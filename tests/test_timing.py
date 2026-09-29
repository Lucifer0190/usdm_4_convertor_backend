"""SoA timing: windows and planned duration (task 6.5), pure parsing (no assembler)."""
from __future__ import annotations

import pytest

from usdm4_assure.soa.timing import (
    Window,
    parse_timepoint,
    parse_window,
    planned_duration_days,
    windows_for_columns,
)


# --- parse_timepoint --------------------------------------------------------- #
@pytest.mark.parametrize("text,value,unit,day_value", [
    ("Day 1", 1, "days", 1),
    ("Day -14", -14, "days", -14),
    ("Week 4", 4, "weeks", 28),
    ("Month 2", 2, "months", 60),
])
def test_parse_timepoint(text, value, unit, day_value):
    tp = parse_timepoint(text, index=0)
    assert (tp.value, tp.unit, tp.day_value) == (value, unit, day_value)


def test_parse_timepoint_falls_back_to_index():
    tp = parse_timepoint("Screening", index=2)
    assert tp.value == 2 and tp.day_value == 2 and tp.text == "Screening"


# --- parse_window ------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("Day 1 (±3 days)", Window(3, 3, "days")),
    ("Day 28 (-3/+7 days)", Window(3, 7, "days")),
    ("Visit 2 (window: ±2 weeks)", Window(2, 2, "weeks")),
    ("Day 1", Window()),
    ("", Window()),
])
def test_parse_window(text, expected):
    assert parse_window(text) == expected


def test_window_defined_property():
    assert not Window().defined
    assert Window(before=1).defined and Window(after=1).defined


def test_window_as_dict():
    assert Window(3, 7, "days").as_dict() == {"before": 3, "after": 7, "unit": "days"}


# --- windows_for_columns ------------------------------------------------------- #
def test_windows_for_columns_never_shorter_than_visits():
    out = windows_for_columns([], ["V1", "V2", "V3"])
    assert out == [{"before": 0, "after": 0, "unit": "days"}] * 3


def test_windows_for_columns_parses_timing_then_falls_back_to_visit_label():
    timings = ["Day 1 (±3 days)", "Day 28", ""]
    visits = ["V1", "V2 (±7 days)", "V3"]
    out = windows_for_columns(timings, visits)
    assert out[0] == {"before": 3, "after": 3, "unit": "days"}   # from timing text
    assert out[1] == {"before": 7, "after": 7, "unit": "days"}   # timing has none: visit label
    assert out[2] == {"before": 0, "after": 0, "unit": "days"}   # neither has one


# --- planned_duration_days ----------------------------------------------------- #
def test_planned_duration_from_first_to_last_timepoint():
    assert planned_duration_days(["Day -14", "Day 1", "Week 4", "Week 12"]) == 14 + 84


def test_planned_duration_none_cases():
    assert planned_duration_days([]) is None
    assert planned_duration_days(["Day 1"]) is None
    assert planned_duration_days(["Day 1", "Day 1"]) is None   # zero span
