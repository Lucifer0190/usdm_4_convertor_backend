"""Deterministic sanity validators — checks a vote count cannot override.

A real run put "Phase 1" into a Phase 3 protocol at confidence 1.00: two regex
members read the same running footer ("Phase 1 2 3 4"), agreed, and outvoted a
correct LLM answer. Agreement between members that share a source is not
evidence. These validators are the independent check: cheap, deterministic,
one question each, and they answer with one of three verdicts.

* ``confirmed`` — the document itself states the value elsewhere (the synopsis
  ``Phase:`` label). This is the only thing that lets a deterministic-only value
  reach ``auto_accept``.
* ``neutral``   — nothing to check against, and the value is plausible in shape.
* ``failed``    — the value is implausible or contradicts the document. Such a
  value is never chosen over a valid one and is never delivered.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Status = Literal["confirmed", "neutral", "failed"]


@dataclass(frozen=True)
class Check:
    status: Status
    reason: str = ""


_OK = Check("neutral")
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4"}
_PHASE_SHAPE = re.compile(r"^(0|[1-4][ab]?|i{1,3}v?|iv)(\s*/\s*([1-4][ab]?|i{1,3}v?|iv))?$")
_SYNOPSIS_PHASE = re.compile(
    r"(?im)^\s*(?:study\s+|trial\s+)?phase\s*:\s*\n?\s*(?:phase\s*)?"
    r"(?P<p>(?:0|[1-4][ab]?|i{1,3}v?|iv)(?:\s*/\s*(?:[1-4][ab]?|i{1,3}v?|iv))?)\s*$")
_ADDRESS = re.compile(
    r"\b(boulevard|blvd|street|avenue|road|suite|floor)\b|\b\d{5}(?:-\d{4})?\b|"
    r"brief title|protocol title|:", re.IGNORECASE)
_TEMPLATE_CODE = re.compile(r"^CT\d+-GSOP|template", re.IGNORECASE)
_TOC_DOTS = re.compile(r"\.{5,}")
_AMENDMENT_TABLE = re.compile(r"description of change|brief rationale|section # and name",
                              re.IGNORECASE)
_LONG_TEXT_FIELDS = {"primaryObjective", "primaryEndpoint", "secondaryObjective",
                     "secondaryEndpoint", "inclusionCriteria", "exclusionCriteria"}


def _phase_key(value: str) -> str:
    v = re.sub(r"\b(phase|trial|study)\b", "", value.lower())
    v = re.sub(r"\s+", "", v)
    return "/".join(_ROMAN.get(part, part) for part in v.split("/"))


def _phase(value: str, doc_text: str) -> Check:
    key = _phase_key(value)
    if not _PHASE_SHAPE.match(key):
        return Check("failed", f"'{value}' is not a trial phase")
    m = _SYNOPSIS_PHASE.search(doc_text)
    if m is None:
        return _OK
    expected = _phase_key(m.group("p"))
    if key == expected:
        return Check("confirmed", "matches the synopsis Phase label")
    return Check("failed", f"contradicts the synopsis Phase label ({m.group('p')})")


def _sponsor(value: str) -> Check:
    if len(value) > 80 or _ADDRESS.search(value):
        return Check("failed", "sponsor looks like an address or a label bleed, not an organisation")
    return _OK


def _identifier(value: str) -> Check:
    if _TEMPLATE_CODE.search(value):
        return Check("failed", "template document code, not a protocol identifier")
    if not 3 <= len(value) <= 40 or value.count(" ") > 5:
        return Check("failed", "implausible protocol identifier")
    return _OK


def _long_text(value: str) -> Check:
    letters = sum(c.isalpha() for c in value)
    if len(value) < 15 or letters < 10 or len(value.split()) < 3:
        return Check("failed", "too short to be an objective, endpoint or criterion list")
    if _TOC_DOTS.search(value):
        return Check("failed", "comes from a table of contents (dot leaders)")
    if _AMENDMENT_TABLE.search(value):
        return Check("failed", "comes from an amendment-history table")
    return _OK


def check(domain: str, field: str, value: str | None, doc_text: str = "") -> Check:
    """Validate one candidate value for one field against the document text.

    ``doc_text`` is the text of the window the field was extracted from (for the
    phase, the title page plus synopsis).
    """
    if not value or not value.strip():
        return _OK                    # absence is handled elsewhere (BLOCK)
    value = value.strip()
    if field == "studyPhase":
        return _phase(value, doc_text)
    if field == "sponsorName":
        return _sponsor(value)
    if field == "protocolIdentifier":
        return _identifier(value)
    if field in _LONG_TEXT_FIELDS:
        return _long_text(value)
    if _TOC_DOTS.search(value):
        return Check("failed", "comes from a table of contents (dot leaders)")
    return _OK
