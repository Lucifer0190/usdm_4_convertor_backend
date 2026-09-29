"""Shared data contracts that flow between layers.

These are the backbone: every module speaks in these types, which is what lets
the Assurance layer treat any extractor's output uniformly.

Phase 1 (DESIGN.md L5–L6) adds grounding: a value is only as good as the verbatim
quote it was drawn from, and the quote's page/offset/bbox are computed by *our*
code from the PDF geometry — never emitted by a model. The types here encode
that rule:

* :class:`CharSpan` / :attr:`Document.chars` — per-page character geometry.
* :class:`Quote` — a resolved quote with the pass that resolved it
  (``exact`` / ``normalized``) or ``failed`` (a hard reject downstream).
* :class:`GroundedCandidate` — one value, one method, one quote.
* :class:`Finding` — a first-class problem (completeness gap, sanitizer repair,
  bounded-repair outcome) that must surface in review, never be swallowed.

The Part 11 audit record lives in :mod:`usdm4_assure.contracts_audit`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# x0, y0, x1, y1 in PDF points, origin top-left (PyMuPDF convention).
BBox = tuple[float, float, float, float]


def bbox_union(boxes: list[BBox]) -> BBox | None:
    """Smallest box enclosing every box in ``boxes`` (``None`` for an empty list)."""
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


# --------------------------------------------------------------------------- #
# Foundation (ingest)
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    """A positioned text block from the source PDF."""
    text: str
    page: int          # 1-indexed
    bbox: BBox
    kind: str = "prose"  # prose | heading | table | footnote


@dataclass(frozen=True)
class CharSpan:
    """One character of a page's text layer with its geometry.

    ``Document.text_of(page)`` is built by concatenating these in order, so a
    character offset into that text *is* an index into ``Document.chars[page]``.
    That equivalence is what lets the quote resolver turn a substring match into
    a bbox without any model involvement.
    """
    char: str
    page: int          # 1-indexed
    bbox: BBox


@dataclass
class Document:
    """The deterministic, cached result of ingest.

    Attributes:
        source: The PDF this was read from.
        blocks: Block-level text with bboxes (heading/table/prose classification).
        full_text: All block text joined — coarse, for retrieval and legacy checks.
        page_images: Rendered page PNGs, if ingest was asked to render.
        chars: Per-page character geometry, ``{page: [CharSpan, ...]}``. Empty
            until the ingest layer populates it (Phase 1.2); grounding needs it.
    """
    source: Path
    blocks: list[Block]
    full_text: str
    page_images: list[Path] = field(default_factory=list)
    chars: dict[int, list[CharSpan]] = field(default_factory=dict)

    def head_text(self, n_pages: int = 2) -> str:
        """Text of the first n pages — where study metadata usually lives."""
        return "\n".join(b.text for b in self.blocks if b.page <= n_pages)

    @property
    def pages(self) -> list[int]:
        """Pages that have character geometry, ascending."""
        return sorted(self.chars)

    def text_of(self, page: int) -> str:
        """Text of ``page`` whose offsets index ``self.chars[page]`` exactly.

        Returns ``""`` when the page has no character geometry — callers must
        not fall back to block text here, because block text does not preserve
        the offset ↔ bbox invariant.
        """
        return "".join(c.char for c in self.chars.get(page, ()))

    def bbox_of(self, page: int, char_start: int, char_end: int) -> BBox | None:
        """Union bbox of ``chars[page][char_start:char_end]`` (``None`` if empty)."""
        spans = self.chars.get(page, [])[char_start:char_end]
        return bbox_union([s.bbox for s in spans])


# --------------------------------------------------------------------------- #
# Extraction -> Assurance
# --------------------------------------------------------------------------- #
class Method(str, Enum):
    """How a candidate value was produced. Drives confidence features and audit."""
    DET_TEXT = "det_text"          # deterministic regex/label/heading logic on text
    DET_TABLE = "det_table"        # deterministic table-grid logic (pdfplumber/PyMuPDF/MinerU)
    LLM_SMALL = "llm_small"        # small model — experimental opt-in only (PLAN.md §4.2)
    LLM_FRONTIER = "llm_frontier"  # frontier text LLM via a config/models.yaml role
    VISION = "vision"              # frontier vision LLM on a page/cell crop
    HUMAN = "human"                # reviewer-supplied value (L9)


class VerifyPass(str, Enum):
    """Which grounding pass located the quote. ``FAILED`` is a hard reject."""
    EXACT = "exact"                # verbatim substring of the page text
    NORMALIZED = "normalized"      # matched after whitespace/ligature/quote normalisation
    FAILED = "failed"              # not found — the value has no defensible source


@dataclass(frozen=True)
class Quote:
    """A verbatim quote resolved to page geometry by deterministic code.

    ``text`` is what the model (or extractor) claimed; ``page``/``char_start``/
    ``char_end`` index ``Document.chars[page]`` and ``bbox`` is the union of those
    characters' boxes. When ``verify_pass`` is ``FAILED`` the location fields are
    ``None`` and the owning candidate must be BLOCKed, not scored.
    """
    text: str
    verify_pass: VerifyPass
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: BBox | None = None

    @property
    def ok(self) -> bool:
        return self.verify_pass is not VerifyPass.FAILED

    @classmethod
    def failed(cls, text: str) -> Quote:
        return cls(text=text, verify_pass=VerifyPass.FAILED)

    def as_row(self) -> dict:
        return {
            "text": self.text,
            "verify_pass": self.verify_pass.value,
            "page": self.page,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "bbox": list(self.bbox) if self.bbox else None,
        }


@dataclass
class FieldCandidate:
    """One value for one field, produced by ONE extraction method.

    **Legacy, ungrounded.** Deterministic extractors still emit these; they carry a
    free-text span but no resolved geometry. Phase 1.5–1.6 migrate every extractor
    to :class:`GroundedCandidate`; until then :func:`to_grounded` bridges the two.
    """
    field: str                 # e.g. "studyTitle"
    value: str | None
    method: str                # e.g. "labels" | "titlepage" | "claude"
    source_text: str = ""      # the span this value was drawn from (for the verifier)
    source_page: int | None = None


@dataclass
class GroundedCandidate:
    """One value for one field, from one method, with its resolved quote.

    Attributes:
        field: USDM-ish field key, e.g. ``"studyTitle"``.
        value: The proposed value (``None`` = method looked and found nothing).
        method: Which kind of process produced it.
        quote: The resolved supporting quote. ``None`` only for ``HUMAN`` values
            and for methods that ran before grounding (bridged legacy candidates);
            everything else must carry one, and a ``FAILED`` quote blocks the value.
        model_id: OpenRouter slug (e.g. ``anthropic/claude-sonnet-4.5``) for LLM/
            vision methods; ``None`` for deterministic and human methods.
        prompt_hash: sha256 of the versioned prompt template + shard spec that
            produced this value; audit needs it to reproduce the call.
        domain: Extraction domain (``metadata`` | ``design`` | ``eligibility`` |
            ``objectives`` | ``soa`` | ...) so review output can group by it.
    """
    field: str
    value: str | None
    method: Method
    quote: Quote | None = None
    model_id: str | None = None
    prompt_hash: str | None = None
    domain: str = ""

    @property
    def grounded(self) -> bool:
        """True when a quote exists and resolved (exact or normalized)."""
        return self.quote is not None and self.quote.ok

    @property
    def page(self) -> int | None:
        return self.quote.page if self.quote else None

    @property
    def bbox(self) -> BBox | None:
        return self.quote.bbox if self.quote else None


def to_grounded(c: FieldCandidate, method: Method, domain: str = "",
                model_id: str | None = None) -> GroundedCandidate:
    """Bridge a legacy :class:`FieldCandidate` into a :class:`GroundedCandidate`.

    The span is carried as an *unresolved* quote (``verify_pass`` is still to be
    decided by the resolver) — so we use ``FAILED`` as the placeholder, which is
    the conservative default: nothing is grounded until the resolver says so.
    """
    quote = Quote.failed(c.source_text) if c.source_text else None
    return GroundedCandidate(field=c.field, value=c.value, method=method,
                             quote=quote, model_id=model_id, domain=domain)


# --------------------------------------------------------------------------- #
# Assurance -> Review
# --------------------------------------------------------------------------- #
class Decision(str, Enum):
    AUTO_ACCEPT = "auto_accept"   # ensemble agreed + verifier supported
    REVIEW = "review"             # disagreement or unsupported -> human
    BLOCK = "block"               # nothing found / hard fail


@dataclass
class AssuredField:
    """A field after the Assurance layer: scored, triaged, provenance-tagged.

    ``quote`` is the resolved quote of the *chosen* value (Phase 1.6 sets it);
    the review row exposes its page/bbox so a reviewer can click-to-source.
    """
    field: str
    value: str | None
    candidates: list[FieldCandidate | GroundedCandidate]
    methods_agree: bool
    n_methods: int
    verifier: str               # supported | partial | unsupported | n/a
    confidence: float           # 0..1, calibrated intent
    decision: Decision
    quote: Quote | None = None
    domain: str = ""
    sanity: str = ""            # validator verdict: "confirmed" | "neutral" | why it failed

    def as_review_row(self) -> dict:
        return {
            "field": self.field,
            "domain": self.domain,
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "decision": self.decision.value,
            "methods_agree": self.methods_agree,
            "n_methods": self.n_methods,
            "verifier": self.verifier,
            "sanity": self.sanity,
            "quote": self.quote.as_row() if self.quote else None,
            "page": self.quote.page if self.quote else None,
            "bbox": list(self.quote.bbox) if self.quote and self.quote.bbox else None,
            "sources": [_source_row(c) for c in self.candidates],
        }


def _source_row(c: FieldCandidate | GroundedCandidate) -> dict:
    if isinstance(c, GroundedCandidate):
        return {"method": c.method.value, "model_id": c.model_id, "page": c.page,
                "value": c.value,
                "span": (c.quote.text[:160] if c.quote else ""),
                "verify_pass": (c.quote.verify_pass.value if c.quote else None)}
    return {"method": c.method, "model_id": None, "page": c.source_page,
            "value": c.value, "span": c.source_text[:160], "verify_pass": None}


# --------------------------------------------------------------------------- #
# Findings — problems that must surface, never be swallowed
# --------------------------------------------------------------------------- #
class FindingKind(str, Enum):
    COMPLETENESS = "completeness"  # expected-vs-found mismatch (L6)
    SANITIZER = "sanitizer"        # we had to repair our own assembler input (L7)
    REPAIR = "repair"              # bounded validate→re-extract loop outcome (L8)
    GROUNDING = "grounding"        # a quote failed to resolve (L5)
    STITCH = "stitch"              # multi-page SoA stitcher ambiguity (L2)
    SCOPE = "scope"                # prohibited-scope evidence filtered (L3)


class Severity(str, Enum):
    INFO = "info"        # recorded, no action needed
    WARNING = "warning"  # reviewer should look
    ERROR = "error"      # blocks auto-accept of the affected field/domain


@dataclass(frozen=True)
class Finding:
    """A first-class quality signal attached to a domain and (optionally) a field."""
    kind: FindingKind
    severity: Severity
    domain: str
    message: str
    field: str | None = None
    expected: str | None = None   # for completeness: what the design implied
    found: str | None = None      # for completeness: what extraction produced

    def as_row(self) -> dict:
        return {"kind": self.kind.value, "severity": self.severity.value,
                "domain": self.domain, "field": self.field, "message": self.message,
                "expected": self.expected, "found": self.found}
