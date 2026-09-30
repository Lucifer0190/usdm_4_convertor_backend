"""Extraction — registry, regulatory and compound identifiers (PLAN.md task C-6).

Every Pfizer protocol sampled (13 of 15 studies checked outside the benchmark set, plus
all 5 train studies — `spikes/_ids_layouts.py`) carries a consistent "Label: value" block
on page 1, immediately around the protocol number C1 metadata already reads: a US IND
number, an EU CT number (or the older EudraCT number, pre-2022 trials), the
ClinicalTrials.gov (NCT) id, sometimes a Pediatric Investigational Plan (PIP) number, and
the sponsor's internal compound number ("Study Intervention Number", one or more
PF-NNNNNNN codes). This module is the rest of that label block.

Deterministic only, front-matter pages only, like every other label-driven member in this
project (`extract/metadata.py`, `extract/sites.py`): the pattern is reliable enough,
measured, that an LLM member would add cost without adding recall.
"""
from __future__ import annotations

import re

from usdm4_assure.contracts import Document, GroundedCandidate, Method
from usdm4_assure.ground.quote import resolve_quote

DOMAIN = "identifiers"
FIELDS = ["nct", "euCt", "eudract", "ind", "pip", "compound"]
FRONT_MATTER_PAGES = 2

_LABELS: dict[str, list[str]] = {
    "nct": [r"clinicaltrials\.gov\s*id"],
    "euCt": [r"\beu\s*ct\s*number"],
    "eudract": [r"\beudract\s*number"],
    "ind": [r"\bus\s*ind\s*number", r"\bind\s*number"],
    "pip": [r"pediatric\s+investigational\s+plan\s+number"],
    "compound": [r"study\s+intervention\s+number"],
}
_NOT_A_VALUE = {"not available", "not applicable", "n/a", "na", "tbd", "unknown",
                "none", "not known", "not app"}
_COMPOUND_CODE = re.compile(r"\bPF-\d{5,8}\b")


def _label_value(line: str) -> str | None:
    if ":" not in line:
        return None
    val = line.split(":", 1)[1].strip(" .")
    return val or None


def _usable(value: str) -> bool:
    return bool(value) and value.strip(" .").lower() not in _NOT_A_VALUE


def extract_labels(doc: Document) -> list[GroundedCandidate]:
    """"Label: value" lines on the front-matter pages; one candidate per field found."""
    out: list[GroundedCandidate] = []
    lines = [ln.strip() for b in doc.blocks if b.page <= FRONT_MATTER_PAGES
             for ln in b.text.splitlines() if ln.strip()]
    for field, patterns in _LABELS.items():
        for line in lines:
            if not any(re.search(p, line, re.IGNORECASE) for p in patterns):
                continue
            val = _label_value(line)
            if field == "compound":
                # A combination-therapy line names the marketed partner drug too ("PF-...,
                # Abemaciclib"); only the sponsor's own PF-code is an identifier here.
                codes = _COMPOUND_CODE.findall(line)
                val = ", ".join(dict.fromkeys(codes)) if codes else None
            if val and _usable(val) and len(val) <= 200:
                out.append(GroundedCandidate(field, val, Method.DET_TEXT,
                                             quote=resolve_quote(doc, line), domain=DOMAIN))
                break
    return out


def extract_identifiers(doc: Document) -> list[GroundedCandidate]:
    return extract_labels(doc)
