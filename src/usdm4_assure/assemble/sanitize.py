"""Assembler-input sanitizer (task 6.3, DESIGN.md L7) — every repair is a Finding.

The usdm4 assembler needs a complete, internally consistent input; extraction
does not always provide one. Until now the gaps were papered over inside
``assemble/study.py`` with silent defaults — a missing phase became
"Phase 1", missing eligibility became the criteria "Adults >= 18 years" /
"Pregnancy", every study got version date 2026-01-01 — and those invented
values reached the USDM output indistinguishable from extracted ones.

This module is now the single place that repairs the input, and it never does
so silently. It keeps the *same* repairs (so assembly behaves exactly as
before) but reports each one as a ``SANITIZER`` finding, graded by what the
repair means:

* ``ERROR`` — a substantive value was invented (phase, protocol identifier,
  eligibility criteria, intervention model): the output is not a faithful
  representation of the protocol until a reviewer supplies it.
* ``WARNING`` — a value was derived or defaulted rather than extracted
  (acronym from the title, a version, the document date, healthy volunteers).
* ``INFO`` — a structural or cosmetic repair (whitespace, truncated label,
  dropped empty item, de-duplicated name).
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from usdm4_assure.contracts import Finding, FindingKind, Severity

STUDY_LABEL_MAX = 120
_WS = re.compile(r"[\s\x00-\x08\x0b\x0c\x0e-\x1f]+")


@dataclass(frozen=True)
class Placeholder:
    path: tuple[str | int, ...]
    value: object
    severity: Severity
    domain: str
    field: str
    reason: str


PLACEHOLDERS: list[Placeholder] = [
    Placeholder(("identification", "titles", "official"), "Untitled Study", Severity.ERROR,
                "metadata", "studyTitle", "study title not extracted"),
    Placeholder(("identification", "identifiers", 0, "identifier"), "SPONSOR-0000",
                Severity.ERROR, "metadata", "protocolIdentifier",
                "sponsor protocol identifier not extracted"),
    Placeholder(("identification", "identifiers", 0, "scope", "non_standard", "name"),
                "Unknown Sponsor", Severity.ERROR, "metadata", "sponsorName",
                "sponsor name not extracted"),
    Placeholder(("identification", "identifiers", 0, "scope", "non_standard", "label"),
                "Unknown Sponsor", Severity.INFO, "metadata", "sponsorName",
                "sponsor label follows the (missing) sponsor name"),
    Placeholder(("identification", "identifiers", 0, "scope", "non_standard", "type"),
                "unknown", Severity.INFO, "metadata", "sponsorType",
                "sponsor organisation type is not extracted (CDISC 'Unknown')"),
    Placeholder(("study_design", "trial_phase"), "Phase 1", Severity.ERROR, "metadata",
                "studyPhase", "study phase not extracted"),
    Placeholder(("study_design", "intervention_model"), "Parallel", Severity.ERROR, "design",
                "interventionModel", "intervention model not extracted"),
    Placeholder(("population", "inclusion_exclusion", "inclusion"), ["Adults >= 18 years"],
                Severity.ERROR, "eligibility", "inclusionCriteria",
                "no inclusion criteria extracted"),
    Placeholder(("population", "inclusion_exclusion", "exclusion"), ["Pregnancy"],
                Severity.ERROR, "eligibility", "exclusionCriteria",
                "no exclusion criteria extracted"),
    Placeholder(("document", "document", "version"), "1", Severity.WARNING, "metadata",
                "studyVersionIdentifier", "protocol version not extracted"),
    Placeholder(("study", "version"), "1", Severity.WARNING, "metadata",
                "studyVersionIdentifier", "protocol version not extracted"),
    Placeholder(("document", "document", "version_date"), "2026-01-01", Severity.WARNING,
                "metadata", "versionDate", "document version date is not extracted"),
    Placeholder(("document", "sections"),
                [{"section_number": "1", "section_title": "Synopsis",
                  "text": "Synopsis extracted from protocol."}],
                Severity.WARNING, "metadata", "documentSections",
                "document narrative sections are not extracted"),
    Placeholder(("population", "demographics", "healthy_volunteers"), False, Severity.WARNING,
                "eligibility", "healthyVolunteers", "healthy-volunteer status is not extracted"),
    Placeholder(("study_design", "rationale"), "Derived from protocol synopsis.", Severity.INFO,
                "design", "rationale", "design rationale is not extracted"),
    Placeholder(("study", "rationale"), "Assembled by USDM4-Assure.", Severity.INFO,
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
            findings.append(_finding(p.severity, p.domain, p.field,
                                     f"{p.reason}; the assembled study carries the placeholder "
                                     f"{p.value!r}.", found=p.value))
    titles = data["identification"]["titles"]
    if _missing(titles.get("brief")):
        titles["brief"] = titles["official"][:20]
        findings.append(_finding(Severity.WARNING, "metadata", "studyAcronym",
                                 "study acronym not extracted; derived from the first 20 "
                                 "characters of the title.", found=titles["brief"]))


def _derive_labels(data: dict, findings: list[Finding]) -> None:
    """Presentation labels follow from the (possibly repaired) acronym and title."""
    acronym = data["identification"]["titles"]["brief"]
    title = data["identification"]["titles"]["official"]
    data["population"]["label"] = data["population"].get("label") or f"{acronym} Population"
    data["study_design"]["label"] = data["study_design"].get("label") or f"{acronym} Design"
    data["study"]["name"] = data["study"].get("name") or {"acronym": acronym}
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
    _derive_labels(clean, findings)
    return clean, findings
