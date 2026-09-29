"""SoA sub-pipeline test: PDF table -> 2 independent extractors -> cross-validation
-> USDM ScheduleTimeline entities, all checked against known ground truth.

Proves the hardest, most safety-critical module: the Schedule of Activities.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_soa_fixture import build, ground_truth

from usdm4_assure.assemble.soa import build_soa
from usdm4_assure.extract.soa.crossval import cross_validate
from usdm4_assure.extract.soa.methods import (
    extract_pdfplumber,
    extract_pymupdf,
    extract_pymupdf_stitched,
    extract_vision,
)
from usdm4_assure.layout.pymupdf_adapter import extract_tables
from usdm4_assure.soa.stitch import stitch


@pytest.fixture(scope="module")
def graded():
    pdf = build()
    gt = ground_truth()
    ag = cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])
    return ag, gt


def test_grid_dimensions_match(graded):
    ag, gt = graded
    assert ag.visits == gt["visits"]
    assert ag.activities == gt["activities"]
    assert ag.epochs == gt["epochs"]


def test_all_cells_correct(graded):
    ag, gt = graded
    got = {(ag.activities[c.activity_i], c.visit_i) for c in ag.present_cells()}
    expected = {(a, vi) for a, marks in gt["marks"].items() for vi in marks}
    assert got == expected, f"missed={expected - got} extra={got - expected}"


def test_two_methods_agree_auto_accept(graded):
    ag, _ = graded
    assert ag.methods == ["pdfplumber", "pymupdf"]
    # every present cell seen by both independent methods -> auto_accept
    assert all(c.decision == "auto_accept" for c in ag.present_cells())


def test_footnote_gated_activity_detected(graded):
    ag, gt = graded
    assert gt["footnote_activity"] in ag.footnote_activities


def test_assembles_to_usdm_scheduletimeline(graded):
    ag, gt = graded
    res = build_soa(ag)
    assert res["assembler_errors"] == []
    s = res["summary"]
    assert s["encounters"] == len(gt["visits"])
    assert s["scheduled_instances"] == len(gt["visits"])
    assert s["conditions"] >= 1          # footnote -> Condition
    assert s["timings"] == len(gt["visits"])


# --- task 2.3/2.7: the stitched-pymupdf path reproduces the single-page path --- #
def test_stitched_pymupdf_matches_legacy_pymupdf_on_a_single_page_table():
    pdf = build()
    old = extract_pymupdf(pdf)
    new = extract_pymupdf_stitched(pdf)
    assert new is not None
    assert (new.epochs, new.visits, new.timings) == (old.epochs, old.visits, old.timings)
    assert new.activities == old.activities
    assert new.cells == old.cells
    assert new.footnote_activities == old.footnote_activities


def test_stitched_pymupdf_cross_validates_identically_to_legacy_path(graded):
    pdf = build()
    ag_old, gt = graded
    ag_new = cross_validate([extract_pdfplumber(pdf), extract_pymupdf_stitched(pdf)])
    assert ag_new.visits == gt["visits"] and ag_new.activities == gt["activities"]
    assert {(ag_new.activities[c.activity_i], c.visit_i) for c in ag_new.present_cells()} == \
           {(ag_old.activities[c.activity_i], c.visit_i) for c in ag_old.present_cells()}


# --- task 2.5: the VLM cell-content pass ---------------------------------------- #
class _StubVisionLLM:
    """A vision-capable member that reads back a pre-scripted sequence of
    replies in call order, simulating a perfect read of each cropped cell."""
    available = True
    name = "vision-stub"

    def __init__(self, replies):
        self._replies = iter(replies)

    def complete_vision(self, image_b64, prompt, **kw):
        return next(self._replies)


def test_extract_vision_reproduces_marks_when_readings_agree():
    from usdm4_assure.soa.from_stitched import is_mark, normalize_header

    pdf = build()
    raw_grid = stitch(extract_tables(pdf)).grids[0]
    normalized = normalize_header(raw_grid)
    # Script the vision stub to read exactly what the grid's own text already
    # says, cell for cell in the same row-major order `extract_vision` reads them.
    scripted = ["X" if is_mark(row[c].text) else "EMPTY"
               for row in normalized.activity_rows() for c in normalized.data_columns()]
    g = extract_vision(pdf, raw_grid, _StubVisionLLM(scripted))
    assert g is not None and g.method == "vision"
    expected = extract_pymupdf(pdf)
    assert (g.activities, g.visits) == (expected.activities, expected.visits)
    assert g.cells == expected.cells  # a perfect vision read reproduces the same marks


def test_extract_vision_returns_none_without_vision_capability():
    pdf = build()
    grid = stitch(extract_tables(pdf)).grids[0]

    class _TextOnly:
        available = True
        name = "text-only"

    assert extract_vision(pdf, grid, _TextOnly()) is None


def test_extract_vision_returns_none_when_llm_unavailable():
    pdf = build()
    grid = stitch(extract_tables(pdf)).grids[0]
    llm = _StubVisionLLM([])
    llm.available = False
    assert extract_vision(pdf, grid, llm) is None


def test_sai_activities_match_ground_truth(graded):
    ag, gt = graded
    res = build_soa(ag)
    by_enc = res["sai_activities_by_encounter"]
    # map each encounter (by timing label) to its expected activity set
    for vi, timing in enumerate(gt["timings"]):
        expected = {a for a, marks in gt["marks"].items() if vi in marks}
        # find the encounter whose activity set matches; assert one does
        assert any(set(acts) == expected for acts in by_enc.values()), (
            f"no SAI matches visit {gt['visits'][vi]} expected {expected}")


# --- task 6.5: real d4k conformance around windows/duration/linking/BC ------------------ #
def test_build_soa_timing_repairs_and_bc_surrogate(graded):
    """Verified against the real d4k rule engine (task 6.5): the assembler's
    own '???' placeholder for an out-of-range window index used to fail
    DDF00006/DDF00025 on every Timing; plannedDuration was hardcoded None
    (DDF00153); Encounter/StudyEpoch were never double-linked (DDF00087/88)."""

    ag, _gt = graded
    result = build_soa(ag)
    assert result["assembler_errors"] == []
    assert any("plannedDuration" in n for n in result["repair_notes"])
    assert any("encounters" in n for n in result["repair_notes"])
    assert any("epochs" in n for n in result["repair_notes"])

    tl = result["entities"]["timelines"][0]
    assert tl.plannedDuration is not None and tl.plannedDuration.quantity.value > 0
    for t in tl.timings:
        assert not (bool(t.windowLabel) ^ bool(t.windowLower) ^ bool(t.windowUpper)) or (
            bool(t.windowLabel) and bool(t.windowLower) and bool(t.windowUpper))
    encounters = result["entities"]["encounters"]
    assert encounters[0].previousId is None
    assert encounters[-1].nextId is None
    assert encounters[1].previousId == encounters[0].id


def test_full_study_timing_rules_pass_against_real_d4k():
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
    from make_full_fixture import build as build_full

    from usdm4_assure.assemble.study import build_full_study
    from usdm4_assure.extract.design import DesignExtract
    from usdm4_assure.extract.soa.crossval import cross_validate as cv
    from usdm4_assure.extract.soa.methods import extract_pdfplumber as epp
    from usdm4_assure.extract.soa.methods import extract_pymupdf as epm

    pdf = build_full()
    grid = cv([epp(pdf), epm(pdf)])
    design = DesignExtract(intervention_model="Parallel",
                           arms=[{"name": "A", "type": "Experimental"},
                                 {"name": "Placebo", "type": "Placebo Comparator"}])
    study = build_full_study([], design, grid)
    assert study["ok"]
    d4k = study["validation"]["d4k"]
    for rule in ("DDF00006", "DDF00025", "DDF00087", "DDF00088", "DDF00153"):
        assert rule not in d4k["failed_rules"], json.dumps(d4k, indent=2)[:2000]
