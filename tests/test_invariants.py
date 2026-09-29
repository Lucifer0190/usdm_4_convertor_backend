"""Structural invariants: quality checks that need no reference labels.

They are what makes generalisation measurable across the 204 real protocols: a schedule
whose visits have no marks, an eligibility list whose numbering skips, an objectives
table with no endpoint are wrong for *any* study, so a failure points at a layout family
the readers do not yet handle, not at one study.
"""
from __future__ import annotations

from usdm4_assure.eval.invariants import (
    eligibility_invariants,
    objectives_invariants,
    soa_invariants,
)
from usdm4_assure.extract.objectives_table import ObjectiveRow
from usdm4_assure.extract.soa.grid import SoAGrid


def _grid(**over):
    base = {
        "method": "geometry",
        "epochs": ["Screening Period", "Treatment Period", "Treatment Period"],
        "visits": ["Day -1 to Day 1", "Day 1", "Day 8"],
        "timings": ["Day -1 to Day 1", "Day 1", "Day 8"],
        "activities": ["GROUP", "Consent", "Vitals", "PK", "ECG", "Labs"],
        "cells": {(1, 0), (2, 0), (2, 1), (2, 2), (3, 1), (4, 1), (5, 2)},
    }
    base.update(over)
    return SoAGrid(**base)


def test_a_sound_schedule_passes_every_invariant():
    r = soa_invariants(_grid(), pages=[20, 21])
    assert all(r.values()), {k: v for k, v in r.items() if not v}


def test_no_grid_fails_the_headline_invariants():
    r = soa_invariants(None, pages=[20])
    assert not r["grid_found"] and not r["enough_visits_and_activities"]


def test_a_visit_column_with_no_mark_at_all_is_flagged():
    r = soa_invariants(_grid(cells={(1, 0), (2, 0), (2, 1)}), pages=[20])
    assert not r["every_visit_has_a_mark"]


def test_placeholder_visit_names_and_missing_epochs_are_flagged():
    r = soa_invariants(_grid(visits=["V1", "Day 1", "Day 8"], epochs=["", "Treatment", "Treatment"]),
                       pages=[20])
    assert not r["visit_names_are_real"] and not r["every_visit_has_an_epoch"]


def test_most_activities_should_be_scheduled_somewhere():
    r = soa_invariants(_grid(activities=["A", "B", "C", "D", "E", "F"], cells={(0, 0)}), pages=[20])
    assert not r["most_activities_are_scheduled"]


def test_marks_must_point_at_real_rows_and_columns():
    r = soa_invariants(_grid(cells={(1, 0), (2, 7)}), pages=[20])
    assert not r["marks_are_in_range"]


def test_eligibility_needs_both_lists_and_plausible_sizes():
    assert all(eligibility_invariants(["a" * 30] * 4, ["b" * 30] * 12).values())
    r = eligibility_invariants([], ["b" * 30] * 12)
    assert not r["has_inclusion"]
    r = eligibility_invariants(["a" * 30] * 4, ["x" * 4000, "y" * 30])
    assert not r["items_are_criterion_sized"]


def test_objectives_need_a_primary_and_endpoints_on_every_row():
    rows = [ObjectiveRow("Primary", "Primary", "Compare A with B.", ["Proportion hospitalised."], None, 1),
            ObjectiveRow("Secondary", "Secondary", "Describe safety.", ["TEAEs."], None, 1)]
    assert all(objectives_invariants(rows).values())
    bad = [ObjectiveRow("Secondary", "Secondary", "Describe safety.", [], None, 1)]
    r = objectives_invariants(bad)
    assert not r["has_a_primary_objective"] and not r["every_row_has_an_endpoint"]
