"""One entry point per extraction domain: extract, then assure (C1-C4).

``run_full`` uses this for its first pass and the bounded repair loop
(:mod:`usdm4_assure.validate.repair`) uses it for every re-extraction, so the
two can never drift apart. A domain's result is both its assured fields (for
triage, review and audit) and the raw extract object the assembler consumes
(``DesignExtract`` / ``EligibilityExtract`` / ``ObjectivesExtract``) — the two
are always produced together, so they stay consistent when the repair loop
adopts a re-extraction.

``escalate`` adds one more ensemble member: a grounded two-pass LLM reading of
the domain (e.g. the ``hard_reasoning`` role on a repair loop's second round).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from usdm4_assure.assure import assure
from usdm4_assure.contracts import AssuredField, Document, FieldCandidate
from usdm4_assure.extract import design as c2
from usdm4_assure.extract import eligibility as c3
from usdm4_assure.extract import metadata as c1
from usdm4_assure.extract import objectives as c4
from usdm4_assure.extract.shards import ELIGIBILITY_FIELDS, OBJECTIVES_FIELDS
from usdm4_assure.llm.base import LLM

DOMAINS = ("metadata", "design", "eligibility", "objectives")


@dataclass
class DomainResult:
    fields: list[AssuredField]
    extract: object = None      # the assembler's input object; None for metadata

    def values(self) -> dict[str, str | None]:
        return {f.field: f.value for f in self.fields}


def eligibility_candidates(e: c3.EligibilityExtract) -> list[FieldCandidate]:
    """Bridge the C3 deterministic extract into field-level candidates for
    :func:`assure`, so eligibility goes through the one uniform assurance path."""
    cands: list[FieldCandidate] = []
    if e.inclusion:
        text = " ".join(e.inclusion)
        cands.append(FieldCandidate("inclusionCriteria", text, "region-parser", text))
    if e.exclusion:
        text = " ".join(e.exclusion)
        cands.append(FieldCandidate("exclusionCriteria", text, "region-parser", text))
    if e.age_min is not None:
        v = str(e.age_min)
        cands.append(FieldCandidate("plannedMinimumAge", v, "region-parser", v))
    if e.age_max is not None:
        v = str(e.age_max)
        cands.append(FieldCandidate("plannedMaximumAge", v, "region-parser", v))
    cands.append(FieldCandidate("plannedSex", e.sex, "region-parser", e.sex))
    return cands


def objectives_candidates(o: c4.ObjectivesExtract) -> list[FieldCandidate]:
    """Bridge the C4 deterministic extract into field-level candidates."""
    cands: list[FieldCandidate] = []
    for item in o.items:
        obj_field = "primaryObjective" if item.level == "Primary" else "secondaryObjective"
        cands.append(FieldCandidate(obj_field, item.objective, "label-parser", item.objective))
        if item.endpoint:
            end_field = "primaryEndpoint" if item.level == "Primary" else "secondaryEndpoint"
            cands.append(FieldCandidate(end_field, item.endpoint, "label-parser", item.endpoint))
    return cands


def _llm_list(escalate) -> list[LLM]:
    if escalate is None:
        return []
    return list(escalate) if isinstance(escalate, Sequence) else [escalate]


def _grounded(module, doc: Document, escalate) -> list:
    """Grounded two-pass candidates from every available escalation member."""
    out: list = []
    for llm in _llm_list(escalate):
        if getattr(llm, "available", False):
            out += module.extract_llm_grounded(doc, llm)
    return out


def extract_domain(domain: str, doc: Document, members: Sequence[LLM],
                   meta: dict | None = None, escalate=None,
                   scoped: dict | None = None) -> DomainResult:
    """Extract and assure one domain over ``doc``.

    Args:
        domain: One of :data:`DOMAINS`.
        doc: The (possibly scoped) document to read.
        members: The run's ensemble LLM members (``[0]`` is the primary).
        meta: Assured metadata values, used by the design extractor.
        escalate: One grounded two-pass LLM member, or several, for this call.
            ``run_full`` passes the ``extract`` (and ``extract_alt``) roles here on
            the first pass; the repair loop passes ``hard_reasoning``.
        scoped: Section-level inputs found by ``sections/slots.py``:
            ``inclusion_doc`` / ``exclusion_doc`` (eligibility) and ``rows``
            (objectives-table rows). Absent keys fall back to reading ``doc``.
    """
    scoped = scoped or {}
    if domain == "metadata":
        cands = c1.extract_all(doc, members) + _grounded(c1, doc, escalate)
        return DomainResult(assure(cands, doc, c1.FIELDS, domain=domain))
    if domain == "design":
        cands, extract = c2.extract_design(doc, meta or {}, members[0])
        cands = cands + _grounded(c2, doc, escalate)
        assured = assure(cands, doc, c2.DESIGN_FIELDS, domain=domain)
        arms = next((f for f in assured if f.field == "armNames"), None)
        if arms is not None and arms.value:
            parsed = c2.arms_from_names(arms.value)
            if parsed:                    # the assured arm list replaces the regex one
                extract.arms, extract.arms_source = parsed, arms.value
                extract.arms_confidence = arms.confidence
                extract.arms_decision = arms.decision.value
        return DomainResult(assured, extract)
    if domain == "eligibility":
        extract = c3.extract_eligibility(doc, scoped.get("inclusion_doc"),
                                         scoped.get("exclusion_doc"))
        cands = eligibility_candidates(extract) + _grounded(c3, doc, escalate)
        return DomainResult(assure(cands, doc, ELIGIBILITY_FIELDS, domain=domain), extract)
    if domain == "objectives":
        extract = c4.extract_objectives(doc, rows=scoped.get("rows"))
        cands = objectives_candidates(extract) + _grounded(c4, doc, escalate)
        return DomainResult(assure(cands, doc, OBJECTIVES_FIELDS, domain=domain), extract)
    raise ValueError(f"unknown extraction domain {domain!r}")
