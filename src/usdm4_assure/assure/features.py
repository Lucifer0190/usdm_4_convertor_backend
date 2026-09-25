"""Multi-signal feature extraction per field (task 4.2, PLAN.md §2.3, DESIGN.md L6).

One :class:`FeatureRow` per :class:`~usdm4_assure.contracts.AssuredField`,
pulling together every signal this codebase already computes but the current
hand-set :func:`usdm4_assure.assure._confidence` formula only partly uses:
grounding outcome (``verify_pass``), the verifier's NLI-ish verdict, ensemble
agreement (both the existing exact-normalized-value vote and a fuzzy
token-overlap measure over the disagreeing values), field type, a retrieval
signal (how much of that domain's evidence window survived scope filtering),
a table-cell flag, grid structural agreement (SoA only), span length, and page
position. Phase 4's :mod:`usdm4_assure.assure.confidence` fits a model on top
of exactly this table — this module only assembles it.

A feature that has no honest signal yet — most obviously OCR detection, which
this codebase does not do — is represented, not invented: ``has_text_layer``
is the real, deterministic thing we *can* say (a page with no character
geometry has no usable text layer, which is the load-bearing half of "would
OCR have been needed here"), and it is documented as such rather than dressed
up as a genuine OCR classifier.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from usdm4_assure.contracts import AssuredField, Document, GroundedCandidate

# FIELD_TYPES lives in eval.labels (task 4.1) as the single source of truth for
# "what shape of value is this field" — the scorer and this feature table must
# agree on it, so it is imported rather than duplicated.
from usdm4_assure.eval.labels import FIELD_TYPES, FieldType
from usdm4_assure.extract.windows import EvidenceWindow

_WORD = re.compile(r"\w+")


def _token_jaccard(a: str, b: str) -> float:
    ta, tb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass(frozen=True)
class FeatureRow:
    """One row of ``features.parquet`` — everything known about one field's decision."""
    study_id: str
    domain: str
    field: str
    field_type: FieldType | str      # "unknown" for a (domain, field) outside FIELD_TYPES
    value_present: bool
    verify_pass: str                 # exact | normalized | failed | none (no quote)
    verifier: str                    # supported | partial | unsupported | n/a
    methods_agree: bool
    n_methods: int
    agreement_fuzzy_mean: float | None  # mean pairwise token-Jaccard across distinct values
    is_table_cell: bool
    grid_agreement: float | None     # SoA structural agreement, 0..1 (None off-SoA)
    span_length: int                 # characters in the resolved quote, 0 if none
    page: int | None
    page_position: float | None      # page / total pages in the document, 0..1
    has_text_layer: bool | None      # real signal: does that page have char geometry at all
    window_kept_ratio: float | None  # retrieval proxy: blocks kept / blocks total in the window
    route_plan_hash: str | None
    confidence: float
    decision: str

    def to_dict(self) -> dict:
        return asdict(self)


def _distinct_values(field_candidates: list) -> list[str]:
    seen, out = set(), []
    for c in field_candidates:
        if c.value and c.value not in seen:
            seen.add(c.value)
            out.append(c.value)
    return out


def _agreement_fuzzy_mean(field_candidates: list) -> float | None:
    values = _distinct_values(field_candidates)
    if len(values) < 2:
        return None
    pairs = [(values[i], values[j]) for i in range(len(values)) for j in range(i + 1, len(values))]
    return sum(_token_jaccard(a, b) for a, b in pairs) / len(pairs)


def _has_text_layer(document: Document | None, page: int | None) -> bool | None:
    if document is None or page is None:
        return None
    return bool(document.chars.get(page))


def extract_features(assured: AssuredField, *, study_id: str = "",
                     document: Document | None = None,
                     window: EvidenceWindow | None = None,
                     grid_agreement: float | None = None) -> FeatureRow:
    """Build one :class:`FeatureRow` from an already-scored :class:`AssuredField`.

    Args:
        assured: The field after :func:`usdm4_assure.assure.assure`.
        study_id: Corpus/study identifier, for joining against labels.
        document: The (possibly scoped) document that field's candidates were
            drawn from — supplies ``has_text_layer`` and ``page_position``.
        window: That domain's :class:`~usdm4_assure.extract.windows.EvidenceWindow`,
            if routing ran — supplies the retrieval proxy and plan hash.
        grid_agreement: SoA cell structural agreement (0..1), if this row is a
            SoA cell; ``None`` for every other domain.
    """
    quote = assured.quote
    winner = next((c for c in assured.candidates
                  if isinstance(c, GroundedCandidate) and c.value == assured.value), None)
    quote = quote or (winner.quote if winner else None)
    page = quote.page if quote else None
    total_pages = len(document.pages) if document is not None and document.pages else None

    return FeatureRow(
        study_id=study_id, domain=assured.domain, field=assured.field,
        field_type=FIELD_TYPES.get((assured.domain, assured.field), "unknown"),
        value_present=assured.value is not None,
        verify_pass=quote.verify_pass.value if quote else "none",
        verifier=assured.verifier,
        methods_agree=assured.methods_agree, n_methods=assured.n_methods,
        agreement_fuzzy_mean=_agreement_fuzzy_mean(assured.candidates),
        is_table_cell=assured.domain == "soa", grid_agreement=grid_agreement,
        span_length=len(quote.text) if quote else 0,
        page=page, page_position=(page / total_pages) if page and total_pages else None,
        has_text_layer=_has_text_layer(document, page),
        window_kept_ratio=(window.blocks_kept / (window.blocks_kept + window.blocks_dropped)
                          if window and (window.blocks_kept + window.blocks_dropped) else None),
        route_plan_hash=window.plan_hash if window else None,
        confidence=assured.confidence, decision=assured.decision.value,
    )


def extract_features_batch(fields: list[AssuredField], *, study_id: str = "",
                           document: Document | None = None,
                           windows: dict[str, EvidenceWindow] | None = None
                           ) -> list[FeatureRow]:
    """One :class:`FeatureRow` per field, looking up each one's domain window."""
    windows = windows or {}
    return [extract_features(a, study_id=study_id, document=document,
                            window=windows.get(a.domain)) for a in fields]


def write_features(rows: list[FeatureRow], path: str | Path) -> Path:
    """Write ``rows`` to Parquet at ``path``.

    Falls back to JSON Lines at the same path with a ``.jsonl`` suffix — with a
    printed note, not a silent switch — when ``pandas``/``pyarrow`` aren't
    installed; features are still useful without them, just not columnar.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
    except ImportError:
        jsonl_path = path.with_suffix(".jsonl")
        jsonl_path.write_text("\n".join(json.dumps(r.to_dict()) for r in rows) + "\n",
                              encoding="utf-8")
        print(f"pandas/pyarrow not installed; wrote {jsonl_path} instead of {path}.")
        return jsonl_path
    pd.DataFrame([r.to_dict() for r in rows]).to_parquet(path, index=False)
    return path
