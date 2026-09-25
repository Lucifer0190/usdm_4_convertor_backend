"""Typed per-field scorer (task 4.1) — compares a pipeline value to a frozen label.

Three verdicts, checked in order, cheapest and strictest first:

* ``exact`` — identical strings, no transformation.
* ``normalized`` — identical after whitespace/case/punctuation normalization
  (``"Phase 2"`` vs ``"phase  2."``).
* ``fuzzy`` — a type-appropriate similarity measure clears a threshold: token
  overlap for ``long_text`` (order-insensitive prose), a numeric tolerance for
  ``number``, ``difflib`` ratio for ``scalar``. Only ``long_text`` and
  ``number`` fields get a fuzzy pass at all — a ``scalar`` field close but not
  normalized-equal (a sponsor's short registry name vs. its full legal name)
  is a deliberate ``miss``, not graded on a curve, since being "close" on a
  short categorical-ish value is usually just wrong.

Anything else is ``miss``. A label with no predicted value is
``predicted_absent`` (not scored as wrong — the caller decides whether that
counts as a gap); a predicted value with no label is skipped entirely by
:func:`score_fields` (nothing to check it against).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from usdm4_assure.eval.labels import FieldLabel, FieldType

Verdict = Literal["exact", "normalized", "fuzzy", "miss", "predicted_absent"]

FUZZY_TEXT_THRESHOLD = 0.5    # token Jaccard, long_text
FUZZY_SCALAR_THRESHOLD = 0.85  # difflib ratio, scalar (used only above normalized)
NUMBER_TOLERANCE = 1.0         # absolute difference, e.g. age in years

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class FieldScore:
    study_id: str
    domain: str
    field: str
    verdict: Verdict
    similarity: float           # 1.0 for exact/normalized, else the measured similarity
    predicted: str | None
    label: str


def normalize(text: str) -> str:
    """Lowercase, punctuation-stripped, whitespace-collapsed."""
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def _token_jaccard(a: str, b: str) -> float:
    ta, tb = set(_WORD.findall(a.lower())), set(_WORD.findall(b.lower()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _number_close(a: str, b: str, tolerance: float = NUMBER_TOLERANCE) -> float | None:
    try:
        return abs(float(a) - float(b))
    except ValueError:
        return None


def score_value(predicted: str | None, label: str, field_type: FieldType
                ) -> tuple[Verdict, float]:
    """``(verdict, similarity)`` for one predicted value against one label value."""
    if predicted is None or predicted == "":
        return "predicted_absent", 0.0
    if predicted == label:
        return "exact", 1.0
    if normalize(predicted) == normalize(label):
        return "normalized", 1.0

    if field_type == "number":
        diff = _number_close(predicted, label)
        if diff is not None and diff <= NUMBER_TOLERANCE:
            return "fuzzy", max(0.0, 1.0 - diff / max(abs(float(label)), 1.0))
        return "miss", 0.0

    if field_type == "long_text":
        sim = _token_jaccard(predicted, label)
        return ("fuzzy", sim) if sim >= FUZZY_TEXT_THRESHOLD else ("miss", sim)

    # scalar: a near-miss on a short value is graded as a miss on principle
    # (see module docstring), but the ratio is still reported for triage.
    sim = SequenceMatcher(a=normalize(predicted), b=normalize(label)).ratio()
    return "miss", sim


def score_field(predicted: str | None, label: FieldLabel) -> FieldScore:
    verdict, sim = score_value(predicted, label.value, label.field_type)
    return FieldScore(study_id=label.study_id, domain=label.domain, field=label.field,
                      verdict=verdict, similarity=sim, predicted=predicted, label=label.value)


def score_fields(predicted: dict[tuple[str, str], str | None], labels: list[FieldLabel]
                 ) -> list[FieldScore]:
    """Score every ``label`` against ``predicted[(domain, field)]`` (``None`` if absent).

    ``predicted`` is keyed by ``(domain, field)`` — the same key
    :class:`~usdm4_assure.contracts.AssuredField` rows carry, so a caller can
    build it straight from a pipeline run's ``review.json`` fields.
    """
    return [score_field(predicted.get((l.domain, l.field)), l) for l in labels]


def summarize(scores: list[FieldScore]) -> dict:
    """Per-verdict counts overall and per domain — the numbers a scoreboard needs."""
    def _tally(items: list[FieldScore]) -> dict:
        counts: dict[str, int] = {}
        for s in items:
            counts[s.verdict] = counts.get(s.verdict, 0) + 1
        n = len(items)
        found = n - counts.get("predicted_absent", 0)
        correct = counts.get("exact", 0) + counts.get("normalized", 0) + counts.get("fuzzy", 0)
        return {"n": n, "verdicts": counts,
               "accuracy": correct / n if n else None,
               "accuracy_of_found": correct / found if found else None}

    domains = sorted({s.domain for s in scores})
    return {"overall": _tally(scores),
           "by_domain": {d: _tally([s for s in scores if s.domain == d]) for d in domains}}
