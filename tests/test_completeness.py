"""Completeness accounting (task 3.6): each rule fires on a crafted mismatch
and stays quiet on consistent input."""
from __future__ import annotations

from usdm4_assure.assure import completeness as cp
from usdm4_assure.contracts import AssuredField, Decision, Finding, FindingKind, Severity
from usdm4_assure.extract.design import DesignExtract
from usdm4_assure.extract.eligibility import EligibilityExtract
from usdm4_assure.extract.objectives import ObjectivePair, ObjectivesExtract
from usdm4_assure.extract.soa.grid import AssuredCell, AssuredGrid, SoAGrid


def _rules(findings: list[Finding]) -> list[str]:
    assert all(f.kind is FindingKind.COMPLETENESS for f in findings)
    return [f.field for f in findings]


# --- arms vs randomization ratio --------------------------------------------------- #
def test_arms_ratio_mismatch_is_error():
    arms = [{"name": "Drug A"}, {"name": "Placebo"}]
    f = cp.check_arms(arms, "randomized 1:1:1 to one of 3 arms: Drug A, Drug B, or Placebo")
    assert _rules(f) == [cp.ARM_COUNT_MATCHES_RATIO]
    assert f[0].severity is Severity.ERROR and (f[0].expected, f[0].found) == ("3", "2")


def test_arms_ratio_consistent_or_absent_is_quiet():
    arms = [{"name": "A"}, {"name": "B"}]
    assert cp.check_arms(arms, "randomized 2:1 to A or B") == []
    assert cp.check_arms(arms, "arms: A or B") == []


# --- arms vs cells ----------------------------------------------------------------- #
def _wrapper(cells: list[tuple[str, str]]) -> dict:
    sd = {"arms": [{"id": "A1"}, {"id": "A2"}], "epochs": [{"id": "E1"}, {"id": "E2"}],
          "studyCells": [{"armId": a, "epochId": e} for a, e in cells]}
    return {"study": {"versions": [{"studyDesigns": [sd]}]}}


def test_missing_study_cell_fires():
    f = cp.check_design_backbone(_wrapper([("A1", "E1"), ("A1", "E2"), ("A2", "E1")]))
    assert _rules(f) == [cp.REQUIRED_DESIGN_BACKBONE_LINKS]
    assert "A2 x E2" in f[0].message and (f[0].expected, f[0].found) == ("4", "3")


def test_full_backbone_and_no_wrapper_are_quiet():
    full = _wrapper([(a, e) for a in ("A1", "A2") for e in ("E1", "E2")])
    assert cp.check_design_backbone(full) == []
    assert cp.check_design_backbone(None) == []
    assert cp.check_design_backbone({"study": {}}) == []


# --- SoA matrix -------------------------------------------------------------------- #
def test_no_matrix_is_error_when_design_exists():
    f = cp.check_schedule([], [], set(), design_present=True)
    assert _rules(f) == [cp.REQUIRED_SCHEDULE_MATRIX] and f[0].severity is Severity.ERROR
    assert cp.check_schedule([], [], set(), design_present=False)[0].severity is Severity.WARNING


def test_unscheduled_activity_and_empty_visit_fire():
    visits, acts = ["V1", "V2", "V3"], ["Consent", "Vitals", "ECG"]
    f = cp.check_schedule(visits, acts, {(0, 0), (1, 0), (1, 1)})
    assert _rules(f) == [cp.REQUIRED_SCHEDULE_LINK_INTEGRITY] * 2
    assert "'ECG'" in f[0].message and "'V3'" in f[1].message


def test_fully_linked_matrix_is_quiet():
    assert cp.check_schedule(["V1", "V2"], ["A", "B"], {(0, 0), (1, 1)}) == []


# --- visits referenced in text vs SoA columns --------------------------------------- #
def test_visit_referenced_in_text_but_not_in_soa_fires():
    f = cp.check_visits_referenced(["Visit 1", "Visit 2 (Day 1)", "V3"],
                                   "At Visit 2 dosing starts; the final assessment is at Visit 5.")
    assert _rules(f) == [cp.VISITS_REFERENCED_IN_SOA]
    assert f[0].expected == "[2, 5]" and f[0].found == "[1, 2, 3]"


def test_unnumbered_soa_or_matching_text_is_quiet():
    assert cp.check_visits_referenced(["Screening", "Day 1", "Week 4"], "Visit 9 happens") == []
    assert cp.check_visits_referenced(["V1", "V2"], "Visit 1 and Visit 2") == []


# --- footnotes ---------------------------------------------------------------------- #
def test_footnote_markers_without_definitions_fire():
    f = cp.check_footnotes({"Vital signs"}, "Vital signs a are collected at every visit.")
    assert _rules(f) == [cp.SOA_FOOTNOTES_DEFINED]


def test_footnotes_defined_or_unused_are_quiet():
    text = "Schedule of Activities\na. Vital signs include blood pressure and pulse.\n"
    assert cp.check_footnotes({"Vital signs"}, text) == []
    assert cp.check_footnotes(set(), "") == []


# --- objectives vs endpoints ---------------------------------------------------------- #
def test_no_primary_objective_is_error():
    f = cp.check_objectives([ObjectivePair("To assess safety", "AEs", "Secondary")])
    assert _rules(f) == [cp.REQUIRED_PRIMARY_OBJECTIVE] and f[0].severity is Severity.ERROR


def test_primary_without_endpoint_and_orphan_secondary_fire():
    f = cp.check_objectives([ObjectivePair("To evaluate efficacy", None, "Primary"),
                             ObjectivePair("To assess PK", None, "Secondary")])
    assert _rules(f) == [cp.REQUIRED_PRIMARY_ENDPOINT, cp.OBJECTIVE_HAS_ENDPOINT]
    assert [x.severity for x in f] == [Severity.ERROR, Severity.WARNING]


def test_paired_objectives_are_quiet():
    assert cp.check_objectives([ObjectivePair("Efficacy", "PASI 75", "Primary"),
                                ObjectivePair("Safety", "AEs", "Secondary")]) == []


# --- eligibility -------------------------------------------------------------------- #
def test_missing_exclusion_list_fires():
    f = cp.check_eligibility(["Adults"], [])
    assert _rules(f) == [cp.ELIGIBILITY_BOTH_LISTS] and "exclusion" in f[0].message
    assert cp.check_eligibility(["Adults"], ["Pregnant"]) == []


# --- orchestration --------------------------------------------------------------------- #
def test_account_accepts_assured_and_raw_grids():
    assured = AssuredGrid(epochs=["E"], visits=["V1", "V2"], timings=["", ""],
                          activities=["A", "B"], footnote_activities=set(), methods=["m"],
                          cells=[AssuredCell(0, 0, True, "both", 1.0, "auto_accept"),
                                 AssuredCell(1, 1, False, "none", 0.2, "review")])
    raw = SoAGrid(method="m", visits=["V1", "V2"], activities=["A", "B"], cells={(0, 0)})
    for grid in (assured, raw):
        rules = _rules(cp.account(grid=grid))
        assert rules == [cp.REQUIRED_SCHEDULE_LINK_INTEGRITY] * 2  # B and V2 unused


def test_account_runs_every_domain():
    design = DesignExtract(arms=[{"name": "A"}], arms_source="randomized 1:1 to A or B")
    got = _rules(cp.account(design=design,
                            eligibility=EligibilityExtract(inclusion=[], exclusion=["x"]),
                            objectives=ObjectivesExtract(items=[])))
    assert got == [cp.ARM_COUNT_MATCHES_RATIO, cp.REQUIRED_PRIMARY_OBJECTIVE,
                   cp.ELIGIBILITY_BOTH_LISTS]


def _field(domain: str, decision: Decision) -> AssuredField:
    return AssuredField(field="f", value="v", candidates=[], methods_agree=True, n_methods=2,
                        verifier="supported", confidence=0.9, decision=decision, domain=domain)


def test_error_finding_demotes_only_that_domains_auto_accepts():
    fields = [_field("design", Decision.AUTO_ACCEPT), _field("design", Decision.BLOCK),
              _field("metadata", Decision.AUTO_ACCEPT)]
    errs = cp.check_arms([{"name": "A"}], "randomized 1:1 to A or B")
    warns = cp.check_eligibility([], [])
    assert cp.demote_on_error(fields, errs + warns) == 1
    assert [f.decision for f in fields] == [Decision.REVIEW, Decision.BLOCK, Decision.AUTO_ACCEPT]
