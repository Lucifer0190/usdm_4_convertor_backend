"""Extraction C3 — eligibility criteria + demographics.

Per DESIGN.md and USDM 4.0, eligibility criteria are stored as FREE TEXT (native
Boolean-logic modelling is a known gap in the standard and an industry-wide ~30%
task — we deliberately do not attempt AND/OR structuring here). We extract the
inclusion/exclusion lists verbatim and the planned age range / sex.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from usdm4_assure.contracts import Document, GroundedCandidate
from usdm4_assure.extract.shards import SHARD_C3_ELIGIBILITY
from usdm4_assure.llm.base import LLM
from usdm4_assure.llm.two_pass import extract_shard

_AGE_RE = re.compile(r"aged?\s+(\d{1,3})\s*(?:to|-|–|through)\s*(\d{1,3})\s*years", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*\d+[.)]\s+")           # split on "1. " / "2) "
_STOP_RE = r"(?:exclusion criteria|schedule of activities|^\s*6\.|\Z)"


@dataclass
class EligibilityExtract:
    inclusion: list[str] = field(default_factory=list)
    exclusion: list[str] = field(default_factory=list)
    age_min: float | None = None
    age_max: float | None = None
    age_unit: str = "Years"
    sex: str = "ALL"
    confidence: float = 0.0
    decision: str = "review"


def _split_items(region: str) -> list[str]:
    """Split a criteria region into individual numbered items."""
    parts = _SPLIT_RE.split(region)
    out = []
    for p in parts:
        s = re.sub(r"\s+", " ", p).strip(" .;:")
        # drop headers / fragments
        if len(s) >= 8 and not s.lower().endswith("criteria"):
            out.append(s + "." if not s.endswith(".") else s)
    return out


def _region(text: str, start_label: str, stop_pat: str) -> str:
    m = re.search(rf"{start_label}\s*:?(?P<body>.*?){stop_pat}",
                  text, re.IGNORECASE | re.DOTALL)
    return m.group("body") if m else ""


_HEADING_TAIL_RE = re.compile(r"\s*\n[^\n]{3,60}:\s*$")
_OPEN_ENDED_RE = re.compile(
    r"(?:≥|>=|at least)\s*(\d{1,3})|(\d{1,3})\s*(?:years?)?\s*(?:of age\s*)?(?:or|and)\s*(?:older|above|over)",
    re.IGNORECASE)
_RANGE_RE = re.compile(
    r"(\d{1,3})\s*(?:to|-|–|through)\s*(<|≤|<=)?\s*(\d{1,3})\s*years?", re.IGNORECASE)


def split_numbered(text: str) -> list[str]:
    """Split a criteria section into items by *sequential* numbering.

    Item ``n`` starts at the next standalone ``n.`` after item ``n-1``, so a
    sub-item ("a."), a date ("Day 28.") or the section title ("5.1.") cannot
    start a criterion, and numbering that skips a number simply ends the list
    (the gap is then visible as a short count rather than a silent mis-split).
    When a number appears more than once before the real item, the occurrence
    preceded by a line break or a wide gap wins over one inside running text.
    """
    starts: list[tuple[int, int]] = []          # (start of "n.", start of the item text)
    pos, n = 0, 1
    while True:
        pattern = re.compile(rf"(?<![\w.,/<>=+≥-])({n})\.(?=\s)\s*")
        found = list(pattern.finditer(text, pos))
        if not found:
            break
        wide = [m for m in found
                if m.start() == 0 or text[m.start() - 1] == "\n"
                or text[max(0, m.start() - 2):m.start()] == "  "]
        m = (wide or found)[0]
        starts.append((m.start(), m.end()))
        pos, n = m.end(), n + 1
    items = []
    for i, (_, body_start) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        item = text[body_start:end]
        item = _HEADING_TAIL_RE.sub("", item.rstrip())
        item = re.sub(r"\s+", " ", item).strip()
        if item:
            items.append(item)
    return items


def age_range(text: str) -> tuple[float | None, float | None]:
    """``(minimum, maximum)`` age in years stated in one criterion, ``None`` if not stated.

    "12 to <18 years ... or >=18 years" is a minimum of 12 with no upper bound: a
    range whose upper end is written "<18" is a sub-group boundary, and an
    open-ended clause (">=18", "at least 18", "18 or older") removes any maximum.
    """
    lows: list[float] = []
    highs: list[float] = []
    for m in _RANGE_RE.finditer(text):
        lows.append(float(m.group(1)))
        if not m.group(2):
            highs.append(float(m.group(3)))
    open_ended = list(_OPEN_ENDED_RE.finditer(text))
    for m in open_ended:
        lows.append(float(m.group(1) or m.group(2)))
    if not lows:
        return None, None
    return min(lows), (None if open_ended or not highs else max(highs))


def extract_eligibility(doc: Document, inclusion_doc: Document | None = None,
                        exclusion_doc: Document | None = None) -> EligibilityExtract:
    e = EligibilityExtract()
    if inclusion_doc is not None or exclusion_doc is not None:
        # Read each list from its own section (sections/slots.py): no table of
        # contents, amendment history or running footer can reach the parser.
        e.inclusion = split_numbered(inclusion_doc.full_text) if inclusion_doc else []
        e.exclusion = split_numbered(exclusion_doc.full_text) if exclusion_doc else []
        text = "\n".join(d.full_text for d in (inclusion_doc, exclusion_doc) if d)
        for item in e.inclusion[:3]:
            lo, hi = age_range(item)
            if lo is not None:
                e.age_min, e.age_max = lo, hi
                break
    else:
        text = doc.full_text
        inc_region = _region(text, r"inclusion criteria", _STOP_RE)
        exc_region = _region(text, r"exclusion criteria",
                             r"(?:schedule of activities|^\s*6\.|\Z)")
        e.inclusion = _split_items(inc_region)
        e.exclusion = _split_items(exc_region)
        if m := _AGE_RE.search(text):
            e.age_min, e.age_max = float(m.group(1)), float(m.group(2))
    # sex: default ALL unless clearly restricted
    if re.search(r"\b(male participants only|men only)\b", text, re.IGNORECASE):
        e.sex = "MALE"
    elif re.search(r"\b(female participants only|women only)\b", text, re.IGNORECASE):
        e.sex = "FEMALE"

    n = len(e.inclusion) + len(e.exclusion)
    e.confidence = 0.8 if (n >= 2 and e.age_min is not None) else (0.6 if n else 0.0)
    e.decision = "auto_accept" if e.confidence >= 0.8 else "review"
    return e


def extract_llm_grounded(doc: Document, llm: LLM) -> list[GroundedCandidate]:
    """Two-pass, quote-grounded eligibility extraction (DESIGN.md L4/L5).

    Independent of the deterministic ``extract_eligibility`` region parser
    above. ``inclusionCriteria``/``exclusionCriteria`` values may be the full
    verbatim criteria block rather than one candidate per item — see
    :mod:`usdm4_assure.extract.shards` for the scoping note.

    Args:
        doc: The ingested protocol document.
        llm: The model member. Returns ``[]`` if unavailable.
    """
    return extract_shard(doc, llm, SHARD_C3_ELIGIBILITY)
