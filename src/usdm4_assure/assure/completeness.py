"""Completeness accounting (task 3.6, L6) — expected vs found, per domain.

Every other assurance signal scores a value that *was* extracted; this one
asks what should have been extracted and was not. Each rule derives an
expectation from one source (design prose, the SoA grid, the objectives
table) and checks it against another, emitting a ``COMPLETENESS``
:class:`Finding` on a mismatch — never a silent pass, never a silent repair.

Rule keys reuse the reference extractor's expectation names where the check
corresponds (``study_validators.evaluate_usdm_against_study_plan``); the
checks themselves are ours, over our extract types.

Severity follows the contract: ``ERROR`` means the domain's output cannot be
trusted as complete, and :func:`demote_on_error` moves that domain's
``auto_accept`` fields to ``review``; ``WARNING`` asks a reviewer to look.
Where a rule has nothing to compare (no numbered visits, no assembled study)
it stays quiet rather than guessing.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from usdm4_assure.contracts import AssuredField, Decision, Finding, FindingKind, Severity

REQUIRED_PRIMARY_OBJECTIVE = "required_primary_objective"
REQUIRED_PRIMARY_ENDPOINT = "required_primary_endpoint"
REQUIRED_SCHEDULE_MATRIX = "required_schedule_matrix"
REQUIRED_SCHEDULE_LINK_INTEGRITY = "required_schedule_link_integrity"
REQUIRED_DESIGN_BACKBONE_LINKS = "required_design_backbone_links"
ARM_COUNT_MATCHES_RATIO = "arm_count_matches_randomization_ratio"
VISITS_REFERENCED_IN_SOA = "visits_referenced_in_soa"
SOA_FOOTNOTES_DEFINED = "soa_footnotes_defined"
OBJECTIVE_HAS_ENDPOINT = "objective_has_endpoint"
ELIGIBILITY_BOTH_LISTS = "eligibility_inclusion_and_exclusion"

_RATIO = re.compile(r"\b(\d+(?::\d+)+)\b")
_VISIT_REF = re.compile(r"\bvisits?\s*(\d{1,3})\b", re.IGNORECASE)
_VISIT_LABEL_NUM = re.compile(r"(?:\bvisit\s*|\bv)(\d{1,3})\b", re.IGNORECASE)
_FOOTNOTE_DEF = re.compile(r"(?m)^\s*[a-z](?:[.)]|\s)\s*[A-Z(]")


def _finding(domain: str, rule: str, severity: Severity, message: str,
             expected: object = None, found: object = None) -> Finding:
    return Finding(FindingKind.COMPLETENESS, severity, domain, message, field=rule,
                   expected=None if expected is None else str(expected),
                   found=None if found is None else str(found))


# --- design --------------------------------------------------------------------- #
def check_arms(arms: list[dict], arms_source: str) -> list[Finding]:
    """A randomization ratio "1:1:1" implies three arms."""
    m = _RATIO.search(arms_source or "")
    if not m:
        return []
    expected = len(m.group(1).split(":"))
    if expected == len(arms):
        return []
    return [_finding("design", ARM_COUNT_MATCHES_RATIO, Severity.ERROR,
                     f"Randomization ratio {m.group(1)} implies {expected} arms but "
                     f"{len(arms)} were extracted.", expected, len(arms))]


def check_design_backbone(wrapper: dict | None) -> list[Finding]:
    """Every arm has a study cell in every epoch (arms x epochs cells)."""
    try:
        sd = wrapper["study"]["versions"][0]["studyDesigns"][0]
    except (TypeError, KeyError, IndexError):
        return []
    arms, epochs, cells = sd.get("arms") or [], sd.get("epochs") or [], sd.get("studyCells") or []
    if not arms:
        return []
    covered = {(c.get("armId"), c.get("epochId")) for c in cells}
    missing = [(a["id"], e["id"]) for a in arms for e in epochs if (a["id"], e["id"]) not in covered]
    if not missing:
        return []
    return [_finding("design", REQUIRED_DESIGN_BACKBONE_LINKS, Severity.WARNING,
                     f"{len(missing)} arm x epoch combination(s) have no study cell "
                     f"(first: {missing[0][0]} x {missing[0][1]}).",
                     len(arms) * len(epochs), len(covered))]


# --- schedule of activities --------------------------------------------------------- #
def check_schedule(visits: list[str], activities: list[str],
                   marked: Iterable[tuple[int, int]], design_present: bool = True) -> list[Finding]:
    """A matrix exists, and every activity row / visit column is used at least once."""
    marked = set(marked)
    if not visits or not activities:
        sev = Severity.ERROR if design_present else Severity.WARNING
        return [_finding("soa", REQUIRED_SCHEDULE_MATRIX, sev,
                         "No schedule-of-activities matrix was extracted.",
                         "visits x activities", f"{len(visits)} x {len(activities)}")]
    out = []
    rows = {a for a, _ in marked}
    cols = {v for _, v in marked}
    empty_rows = [activities[i] for i in range(len(activities)) if i not in rows]
    empty_cols = [visits[i] for i in range(len(visits)) if i not in cols]
    if empty_rows:
        out.append(_finding("soa", REQUIRED_SCHEDULE_LINK_INTEGRITY, Severity.WARNING,
                            f"{len(empty_rows)} activit(y/ies) scheduled at no visit, e.g. "
                            f"'{empty_rows[0]}' — marks may have been lost in extraction.",
                            len(activities), len(activities) - len(empty_rows)))
    if empty_cols:
        out.append(_finding("soa", REQUIRED_SCHEDULE_LINK_INTEGRITY, Severity.WARNING,
                            f"{len(empty_cols)} visit(s) with no scheduled activity, e.g. "
                            f"'{empty_cols[0]}'.", len(visits), len(visits) - len(empty_cols)))
    return out


def check_visits_referenced(visits: list[str], evidence_text: str) -> list[Finding]:
    """Numbered visits the protocol text refers to must be SoA columns.

    Only runs when the SoA labels its columns with visit numbers at all —
    "Screening / Day 1 / Week 4" columns give nothing to compare against.
    """
    in_soa = {int(n) for v in visits for n in _VISIT_LABEL_NUM.findall(v)}
    if not in_soa:
        return []
    referenced = {int(n) for n in _VISIT_REF.findall(evidence_text or "")}
    missing = sorted(referenced - in_soa)
    if not missing:
        return []
    return [_finding("soa", VISITS_REFERENCED_IN_SOA, Severity.WARNING,
                     f"Protocol text refers to visit(s) {missing[:8]} that are not SoA columns "
                     f"(SoA visits: {sorted(in_soa)[:12]}).", sorted(referenced), sorted(in_soa))]


def check_footnotes(footnote_activities: Iterable[str], evidence_text: str) -> list[Finding]:
    """Activities carrying a footnote marker need footnote definitions somewhere."""
    marked = sorted(footnote_activities)
    if not marked or _FOOTNOTE_DEF.search(evidence_text or ""):
        return []
    return [_finding("soa", SOA_FOOTNOTES_DEFINED, Severity.WARNING,
                     f"{len(marked)} SoA activit(y/ies) carry footnote markers (e.g. "
                     f"'{marked[0]}') but no footnote definitions were found.",
                     "footnote definitions", "none")]


# --- objectives / eligibility --------------------------------------------------------- #
def check_objectives(items: list) -> list[Finding]:
    """A primary objective exists, it has a primary endpoint, and every objective has one."""
    primary = [i for i in items if (i.level or "").lower() == "primary"]
    if not primary:
        return [_finding("objectives", REQUIRED_PRIMARY_OBJECTIVE, Severity.ERROR,
                         "No primary objective was extracted.", ">=1", 0)]
    out = []
    if not any(i.endpoint for i in primary):
        out.append(_finding("objectives", REQUIRED_PRIMARY_ENDPOINT, Severity.ERROR,
                            "The primary objective has no extracted endpoint.", ">=1", 0))
    orphans = [i for i in items if i not in primary and not i.endpoint]
    if orphans:
        out.append(_finding("objectives", OBJECTIVE_HAS_ENDPOINT, Severity.WARNING,
                            f"{len(orphans)} objective(s) without an endpoint, e.g. "
                            f"'{orphans[0].objective[:80]}'.", len(items), len(items) - len(orphans)))
    return out


def check_eligibility(inclusion: list[str], exclusion: list[str]) -> list[Finding]:
    missing = [name for name, items in (("inclusion", inclusion), ("exclusion", exclusion))
               if not items]
    if not missing:
        return []
    return [_finding("eligibility", ELIGIBILITY_BOTH_LISTS, Severity.WARNING,
                     f"No {' or '.join(missing)} criteria were extracted.",
                     "inclusion and exclusion", ", ".join(missing) + " empty")]


# --- orchestration -------------------------------------------------------------------- #
def account(*, design=None, grid=None, eligibility=None, objectives=None,
            wrapper: dict | None = None, evidence_text: str = "") -> list[Finding]:
    """Run every rule whose inputs are present; returns all findings.

    Args:
        design: ``DesignExtract`` (arms + the sentence they were parsed from).
        grid: ``AssuredGrid`` / ``SoAGrid`` (visits, activities, marked cells).
        eligibility: ``EligibilityExtract``.
        objectives: ``ObjectivesExtract``.
        wrapper: The assembled USDM wrapper, for the arms x epochs check.
        evidence_text: Current-scope protocol text (a routed window's
            ``full_text``), so historic sections cannot manufacture a
            "missing visit".
    """
    out: list[Finding] = []
    if design is not None:
        out += check_arms(design.arms, design.arms_source)
    out += check_design_backbone(wrapper)
    if grid is not None:
        marked = ([(c.activity_i, c.visit_i) for c in grid.cells if c.present]
                  if isinstance(grid.cells, list) else grid.cells)
        out += check_schedule(grid.visits, grid.activities, marked, design is not None)
        out += check_visits_referenced(grid.visits, evidence_text)
        out += check_footnotes(grid.footnote_activities, evidence_text)
    if objectives is not None:
        out += check_objectives(objectives.items)
    if eligibility is not None:
        out += check_eligibility(eligibility.inclusion, eligibility.exclusion)
    return out


def demote_on_error(fields: list[AssuredField], findings: list[Finding]) -> int:
    """Move ``auto_accept`` fields of any domain with an ERROR finding to ``review``.

    Returns how many fields were demoted.
    """
    bad = {f.domain for f in findings if f.severity is Severity.ERROR}
    n = 0
    for a in fields:
        if a.domain in bad and a.decision is Decision.AUTO_ACCEPT:
            a.decision = Decision.REVIEW
            n += 1
    return n
