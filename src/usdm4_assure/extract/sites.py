"""Extraction C6 — organizations and study roles (task 6.4).

PLAN.md calls this the weakest published category, and the corpus bears that
out: a physical site roster (name/address/country per investigational site)
essentially never appears in the protocol body itself — it lives in a
site-management system the protocol PDF doesn't carry. What the protocol text
*does* usually name, in the same front-matter block as the sponsor, is the
organizations running the study around the sponsor: a Contract Research
Organization (CRO) and a central/reference laboratory. Those are what this
module extracts; a genuine site roster, when one is present, is out of scope
here and reported as absent rather than guessed at.

Two independent members, the same shape as every other domain (C1-C5):

* a deterministic label parser, restricted to a short list of role labels on
  the front-matter pages only (so it does not fire on an unrelated
  "Laboratory Assessments" section heading deep in the protocol body);
* an optional grounded two-pass LLM member, every value quote-grounded like
  every other domain — a candidate whose quote fails to resolve is ungrounded,
  not a name to trust.

Candidates flow through the same :func:`usdm4_assure.assure.assure` as every
other domain; there is no bespoke confidence rule here.
"""
from __future__ import annotations

import re

from usdm4_assure.contracts import Document, GroundedCandidate, Method
from usdm4_assure.ground.quote import resolve_quote
from usdm4_assure.llm.base import LLM
from usdm4_assure.llm.two_pass import run_two_pass, template_hash

DOMAIN = "sites"
PROMPT_ID = "c6_sites"
FIELDS = ["croName", "centralLaboratoryName"]
FRONT_MATTER_PAGES = 5

_LABELS: dict[str, list[str]] = {
    "croName": [r"contract research organi[sz]ation", r"\bCRO\b"],
    "centralLaboratoryName": [r"central laboratory", r"reference laboratory",
                              r"central lab\b"],
}


def _label_value(line: str) -> str | None:
    if ":" in line:
        val = line.split(":", 1)[1].strip(" .")
        return val or None
    return None


def extract_labels(doc: Document) -> list[GroundedCandidate]:
    """"Label: Organization Name" lines, front-matter pages only — same
    restriction as, and for the same reason as, ``metadata.extract_labels``."""
    out: list[GroundedCandidate] = []
    lines = [ln.strip() for b in doc.blocks if b.page <= FRONT_MATTER_PAGES
             for ln in b.text.splitlines() if ln.strip()]
    for field, patterns in _LABELS.items():
        for line in lines:
            if any(re.search(p, line, re.IGNORECASE) for p in patterns):
                val = _label_value(line)
                if val and 1 <= len(val) <= 200:
                    out.append(GroundedCandidate(field, val, Method.DET_TEXT,
                                                 quote=resolve_quote(doc, line), domain=DOMAIN))
                    break
    return out


def extract_llm_grounded(doc: Document, llm: LLM) -> list[GroundedCandidate]:
    """A grounded LLM member's own reading of the same two fields.

    Returns ``[]`` if the member is unavailable or either pass fails to
    produce parseable output — mirrors every other domain's grounded path.
    """
    if not getattr(llm, "available", False):
        return []
    items = run_two_pass(llm, PROMPT_ID, doc.head_text(3)[:8000], fields=", ".join(FIELDS))
    if items is None:
        return []
    phash = template_hash(PROMPT_ID)
    model_id = getattr(llm, "model", None) or getattr(llm, "name", None)
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        field, value = item.get("field"), item.get("value")
        if field not in FIELDS or not value:
            continue
        quote_text = item.get("quote") or ""
        quote = resolve_quote(doc, quote_text) if quote_text else None
        out.append(GroundedCandidate(field, str(value).strip(), Method.LLM_FRONTIER,
                                     quote=quote, model_id=model_id, prompt_hash=phash,
                                     domain=DOMAIN))
    return out


def extract_sites(doc: Document, llm: LLM | None = None) -> list[GroundedCandidate]:
    """The deterministic member, plus the LLM member if one is given."""
    cands = extract_labels(doc)
    if llm is not None:
        cands += extract_llm_grounded(doc, llm)
    return cands
