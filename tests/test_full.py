"""Full-loop test: one protocol PDF -> complete USDM 4.0 study (metadata + design + SoA).

Proves the domains compose into one conformant, structurally-valid study.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_full_fixture import build, ground_truth

from usdm4_assure.pipeline import run_full


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    build()
    out = tmp_path_factory.mktemp("full")
    return run_full("data/fixtures/protocol_full.pdf", out_dir=out)


def test_assembles_without_errors(result):
    assert result.study["ok"] is True
    assert result.study["assembler_errors"] == []


def test_structural_gate_passes(result):
    assert result.study["validation"]["structural"]["passed"] is True


def test_design_arms_extracted(result):
    gt = ground_truth()
    got = [a["name"] for a in result.design.arms]
    assert got == [a["name"] for a in gt["arms"]]
    assert result.design.intervention_model == gt["interventionModel"]


def test_study_contains_design_and_soa(result):
    s = result.study["summary"]
    assert s["arms"] == 3
    assert s["encounters"] == 5
    assert s["scheduled_instances"] == 5
    assert s["epochs"] == 3


def test_phase_resolved_to_cdisc_code(result):
    phase = result.study["summary"]["study_phase"]
    # C15601 = Phase II Trial
    assert isinstance(phase, dict) and phase.get("code") == "C15601"


def test_eligibility_extracted(result):
    gt = ground_truth()
    assert len(result.eligibility.inclusion) == len(gt["inclusion"])
    assert len(result.eligibility.exclusion) == len(gt["exclusion"])
    assert result.eligibility.age_min == gt["age_min"]
    assert result.eligibility.age_max == gt["age_max"]


def test_objectives_extracted(result):
    assert len(result.objectives.items) >= 1
    prim = result.objectives.items[0]
    assert prim.level == "Primary"
    assert prim.endpoint is not None


def test_study_populated_with_design_domains(result):
    """Interventions + population demographics land in the assembled study."""
    sv = result.study["wrapper"]["study"]["versions"][0]
    assert len(sv.get("studyInterventions", [])) == 3
    sd = sv["studyDesigns"][0]
    pop = sd.get("population", {})
    # planned age range present (clears DDF00097)
    assert pop.get("plannedAge") is not None or pop.get("plannedSex")


def test_review_records_route_plan(result):
    import json
    review = json.loads((result.out_dir / "review.json").read_text(encoding="utf-8"))
    assert review["routing"]["route_plan_hash"] == result.routed.plan_hash
    assert set(review["routing"]["windows"]) == {"metadata", "design", "eligibility", "objectives"}
    assert isinstance(review["findings"], list)


def test_complete_protocol_has_no_completeness_findings(result):
    # False-positive guard for task 3.6: the fixture is a complete protocol.
    assert [f for f in result.findings if f.kind.value == "completeness"] == []
