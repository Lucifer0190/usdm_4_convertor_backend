"""Assembler-input sanitizer (task 6.3, DESIGN.md L7) — every repair is a Finding.

The usdm4 assembler needs *type-correct* input (a `str` field cannot hold `None`), but not
a *complete* one: every field this module fills is optional in `usdm4`'s own assembler-input
schema (`str = ""` / `list = []`), confirmed empirically in `spikes/_sanitize_probe.py` — the
assembler runs to completion with each one genuinely empty. So gaps are filled with the
type's own empty value, never with text that reads like a real answer: a missing phase is
left `""`, not turned into "Phase 1"; missing eligibility is left `[]`, not the invented
criteria "Adults >= 18 years" / "Pregnancy"; a missing document date is left `""`, not
"2026-01-01" (PLAN.md task C-8 — earlier versions of this module did fabricate those values,
indistinguishable in the delivered JSON from a real extraction).

The one field a genuine "unknown" cannot be left empty for is `healthy_volunteers`
(`bool`, no null state in the schema): it keeps its `False` default, which is also
`usdm4`'s own schema default, and is still reported so a reviewer knows it was not read
from the protocol. The sponsor organisation's CDISC `type` code similarly keeps the
literal string "unknown" — that is the controlled-terminology decode *for* not knowing
the type, not an invented fact.

Every repair reported as a ``SANITIZER`` finding, graded by what the gap means:

* ``ERROR`` — a substantive field was left empty (phase, protocol identifier, sponsor
  name, title, eligibility criteria, intervention model): the output is not a faithful
  representation of the protocol until a reviewer supplies it.
* ``WARNING`` — a field was left empty or derived rather than extracted (acronym from
  the title, a version, the document date, narrative sections, healthy volunteers).
* ``INFO`` — a structural or cosmetic repair (whitespace, truncated label, dropped
  empty item, de-duplicated name, the sponsor's CDISC "unknown" type code).
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from usdm4_assure.contracts import Finding, FindingKind, Severity

STUDY_LABEL_MAX = 120
_WS = re.compile(r"[\s\x00-\x08\x0b\x0c\x0e-\x1f]+")
# usdm4's `Organization` and `Study` both derive from `ApiBaseModelWithIdAndName`, whose
# `name: str = Field(min_length=1)` the pinned library enforces at build time (not merely
# in the assembler-input schema): an empty name aborts the *entire* assembly, which is a
# worse outcome than one flagged field. This is the one value substituted when there is
# truly nothing to fall back to (not even an acronym or protocol identifier) — bracketed
# and lower-case so it cannot be mistaken for extracted content.
_UNRESOLVABLE = "[not extracted]"


@dataclass(frozen=True)
class Placeholder:
    path: tuple[str | int, ...]
    value: object
    severity: Severity
    domain: str
    field: str
    reason: str


PLACEHOLDERS: list[Placeholder] = [
    Placeholder(("identification", "titles", "official"), "", Severity.ERROR,
                "metadata", "studyTitle", "study title not extracted"),
    Placeholder(("identification", "identifiers", 0, "identifier"), "",
                Severity.ERROR, "metadata", "protocolIdentifier",
                "sponsor protocol identifier not extracted"),
    Placeholder(("identification", "identifiers", 0, "scope", "non_standard", "name"),
                "", Severity.ERROR, "metadata", "sponsorName",
                "sponsor name not extracted"),
    Placeholder(("identification", "identifiers", 0, "scope", "non_standard", "label"),
                "", Severity.INFO, "metadata", "sponsorName",
                "sponsor label follows the (missing) sponsor name"),
    # "unknown" is the CDISC controlled-terminology decode for an organisation of
    # unrecorded type, not an invented fact — the one placeholder that stays non-empty.
    Placeholder(("identification", "identifiers", 0, "scope", "non_standard", "type"),
                "unknown", Severity.INFO, "metadata", "sponsorType",
                "sponsor organisation type is not extracted (CDISC 'Unknown')"),
    Placeholder(("study_design", "trial_phase"), "", Severity.ERROR, "metadata",
                "studyPhase", "study phase not extracted"),
    Placeholder(("study_design", "intervention_model"), "", Severity.ERROR, "design",
                "interventionModel", "intervention model not extracted"),
    Placeholder(("population", "inclusion_exclusion", "inclusion"), [],
                Severity.ERROR, "eligibility", "inclusionCriteria",
                "no inclusion criteria extracted"),
    Placeholder(("population", "inclusion_exclusion", "exclusion"), [],
                Severity.ERROR, "eligibility", "exclusionCriteria",
                "no exclusion criteria extracted"),
    Placeholder(("document", "document", "version"), "", Severity.WARNING, "metadata",
                "studyVersionIdentifier", "protocol version not extracted"),
    Placeholder(("study", "version"), "", Severity.WARNING, "metadata",
                "studyVersionIdentifier", "protocol version not extracted"),
    Placeholder(("document", "document", "version_date"), "", Severity.WARNING,
                "metadata", "versionDate", "document version date is not extracted"),
    Placeholder(("document", "sections"), [], Severity.WARNING, "metadata",
                "documentSections", "document narrative sections are not extracted"),
    # `bool` has no "unknown" state in the schema; `False` is both the conservative
    # clinical-trial default (assume a patient population, not healthy volunteers)
    # and usdm4's own schema default, so this is a genuine default, not an invented fact.
    Placeholder(("population", "demographics", "healthy_volunteers"), False, Severity.WARNING,
                "eligibility", "healthyVolunteers", "healthy-volunteer status is not extracted"),
    Placeholder(("study_design", "rationale"), "", Severity.INFO,
                "design", "rationale", "design rationale is not extracted"),
    Placeholder(("study", "rationale"), "", Severity.INFO,
                "metadata", "rationale", "study rationale is not extracted"),
]


def _finding(severity: Severity, domain: str, field: str, message: str,
             found: object = None) -> Finding:
    return Finding(FindingKind.SANITIZER, severity, domain, message, field=field,
                   expected="extracted value", found=None if found is None else str(found))


def _get(data: dict, path: tuple) -> object:
    node = data
    for key in path:
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def _set(data: dict, path: tuple, value: object) -> None:
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def _missing(value: object) -> bool:
    return value is None or value == "" or value == []


def _fill_placeholders(data: dict, findings: list[Finding]) -> None:
    for p in PLACEHOLDERS:
        if _missing(_get(data, p.path)):
            _set(data, p.path, copy.deepcopy(p.value))
            note = ("the field is left empty; the assembled study does not carry an "
                    "invented value." if _missing(p.value) else
                    f"the assembled study carries the value {p.value!r} (not extracted).")
            findings.append(_finding(p.severity, p.domain, p.field, f"{p.reason}; {note}",
                                     found=p.value if not _missing(p.value) else None))
    titles = data["identification"]["titles"]
    if _missing(titles.get("brief")):
        titles["brief"] = titles["official"][:20]
        findings.append(_finding(Severity.WARNING, "metadata", "studyAcronym",
                                 "study acronym not extracted; derived from the first 20 "
                                 "characters of the title.", found=titles["brief"]))


def _fill_required_names(data: dict, findings: list[Finding]) -> None:
    """The one place ``_UNRESOLVABLE`` can be used: usdm4's ``Organization.name`` cannot
    be empty (see the constant's docstring). Every other repair leaves a real gap empty."""
    org = data["identification"]["identifiers"][0]["scope"]["non_standard"]
    if _missing(org.get("name")):
        org["name"] = _UNRESOLVABLE
        findings.append(_finding(
            Severity.ERROR, "metadata", "sponsorName",
            "sponsor name not extracted, and usdm4 requires a non-empty organisation "
            f"name; the sentinel {_UNRESOLVABLE!r} is used so assembly can proceed."))


def _derive_labels(data: dict, findings: list[Finding]) -> None:
    """Presentation labels follow from the (possibly empty) acronym and title.

    The acronym/title may now genuinely be "" (task C-8): a label is still built for
    every USDM object that needs one, but never with a leading "" prefix or other
    artifact of a blank source string.
    """
    acronym = data["identification"]["titles"]["brief"]
    title = data["identification"]["titles"]["official"]
    prefix = f"{acronym} " if acronym else ""
    data["population"]["label"] = data["population"].get("label") or f"{prefix}Population"
    data["study_design"]["label"] = data["study_design"].get("label") or f"{prefix}Design"
    if not data["study"].get("name"):
        # usdm4's Study.name is a required, non-empty internal identifier: the assembler
        # itself tries name.identifier, then .acronym, then .compound (StudyAssembler.
        # _get_study_name_label), so real extracted content (the acronym, or failing that
        # the protocol identifier) is preferred; _UNRESOLVABLE is the last resort, used
        # only when neither was extracted.
        protocol_id = _get(data, ("identification", "identifiers", 0, "identifier")) or ""
        source = acronym or protocol_id
        data["study"]["name"] = {"acronym": source or _UNRESOLVABLE}
        if not source:
            findings.append(_finding(
                Severity.ERROR, "metadata", "studyTitle",
                "neither a title nor a protocol identifier was extracted, and usdm4 "
                f"requires a non-empty internal study name; the sentinel {_UNRESOLVABLE!r} "
                "is used so assembly can proceed."))
    label = data["study"].get("label") or title
    if len(label) > STUDY_LABEL_MAX:
        findings.append(_finding(Severity.INFO, "metadata", "studyTitle",
                                 f"study label truncated to {STUDY_LABEL_MAX} characters."))
    data["study"]["label"] = label[:STUDY_LABEL_MAX]


def _normalize_text(node: object, counter: list[int]) -> object:
    if isinstance(node, str):
        clean = _WS.sub(" ", node).strip()
        counter[0] += clean != node
        return clean
    if isinstance(node, list):
        return [_normalize_text(v, counter) for v in node]
    if isinstance(node, dict):
        return {k: _normalize_text(v, counter) for k, v in node.items()}
    return node


def _dedupe_arms(design: dict, findings: list[Finding]) -> None:
    """Drop unnamed arms; make duplicate arm/intervention names unique, positionally."""
    arms = [a for a in design.get("arms", []) if a.get("name")]
    interventions = [i for i in design.get("interventions", []) if i.get("name")]
    if len(arms) != len(design.get("arms", [])):
        findings.append(_finding(Severity.WARNING, "design", "arms",
                                 f"{len(design['arms']) - len(arms)} unnamed arm(s) dropped."))
    design["interventions"] = interventions
    # One intervention per arm, same order (assemble.study._interventions_from_arms).
    paired = interventions if len(interventions) == len(arms) else [None] * len(arms)
    seen: dict[str, int] = {}
    for arm, intervention in zip(arms, paired, strict=True):
        name = arm["name"]
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            new = f"{name} ({seen[name]})"
            findings.append(_finding(Severity.INFO, "design", "arms",
                                     f"duplicate arm name '{name}' renamed to '{new}'."))
            arm["name"] = new
            arm["intervention_names"] = [new if n == name else n
                                         for n in arm.get("intervention_names", [])]
            if intervention is not None and intervention.get("name") == name:
                intervention["name"] = new
    design["arms"] = arms


def _drop_empty_objectives(block: dict | None, findings: list[Finding]) -> None:
    if not block:
        return
    kept = []
    for obj in block.get("objectives", []):
        if not obj.get("text"):
            findings.append(_finding(Severity.WARNING, "objectives", "objectives",
                                     "objective with no text dropped."))
            continue
        obj["endpoints"] = [e for e in obj.get("endpoints", []) if e.get("text")]
        kept.append(obj)
    block["objectives"] = kept
    names = {e.get("name") for o in kept for e in o["endpoints"] if e.get("name")}
    estimands = [e for e in block.get("estimands", []) if e.get("endpoint_name") in names]
    if len(estimands) != len(block.get("estimands", [])):
        findings.append(_finding(Severity.WARNING, "estimands", "estimands",
                                 "estimand(s) referencing a dropped endpoint removed."))
    block["estimands"] = estimands


def _drop_empty_criteria(population: dict, findings: list[Finding]) -> None:
    ie = population.setdefault("inclusion_exclusion", {"inclusion": [], "exclusion": []})
    for kind in ("inclusion", "exclusion"):
        items = ie.get(kind) or []
        kept = [c for c in items if (c if isinstance(c, str) else c.get("text", ""))]
        if len(kept) != len(items):
            findings.append(_finding(Severity.INFO, "eligibility", f"{kind}Criteria",
                                     f"{len(items) - len(kept)} empty {kind} criterion dropped."))
        ie[kind] = kept


def sanitize(data: dict) -> tuple[dict, list[Finding]]:
    """A repaired deep copy of an ``AssemblerInput``-shaped dict, plus its findings."""
    findings: list[Finding] = []
    counter = [0]
    clean = _normalize_text(copy.deepcopy(data), counter)
    if counter[0]:
        findings.append(_finding(Severity.INFO, "metadata", "text",
                                 f"whitespace/control characters normalized in {counter[0]} "
                                 "string(s)."))
    _drop_empty_criteria(clean["population"], findings)
    _dedupe_arms(clean["study_design"], findings)
    _drop_empty_objectives(clean.get("objectives"), findings)
    _fill_placeholders(clean, findings)
    _fill_required_names(clean, findings)
    _derive_labels(clean, findings)
    return clean, findings
