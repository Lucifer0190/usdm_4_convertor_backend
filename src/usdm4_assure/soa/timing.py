"""SoA timing: visit windows and planned duration (task 6.5, conformance.md Bucket 2).

Pure text parsing, independent of the assembler, so it is unit-testable on its
own. Two things this module exists to get right:

1. **An empty windows array is not "no windows" to the usdm4 assembler — it is
   a missing-input placeholder.** ``TimelineAssembler._window_label()``
   returns the literal string ``"???"`` for any timepoint index past the end
   of the supplied ``windows.items`` list. That non-empty placeholder reads as
   a *defined* window label with no matching lower/upper bound, which fails
   DDF00006 (all-or-nothing) on every timing, and DDF00025 (no window on the
   anchor) on the anchor timing specifically — confirmed against the real d4k
   rule engine, not inferred. The fix has nothing to do with parsing real
   tolerance windows: it is supplying one all-zero :class:`Window` per
   timepoint, which the assembler renders as a proper empty label.
2. Real tolerance windows ("Day 1 (±3 days)", "Day 28 (-3/+7 days)") are
   parsed when present, which is the actual timing-window *data* this task
   asks for, on top of the placeholder-bug fix above.

:func:`planned_duration_days` covers DDF00153: the assembler's own
``ScheduleTimeline.plannedDuration`` is hardcoded to ``None`` (there is no
input field for it at all), so it can only be filled by mutating the
assembled object afterward (:func:`usdm4_assure.assemble.soa.repair_timeline`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The exact parse assemble.soa.grid_to_timeline_input has always used for a
# timepoint's day value, so window/duration math agrees with what the
# assembler's own anchor-finding sees.
_TIME_RE = re.compile(r"(day|week|month)\s*(-?\d+)", re.IGNORECASE)
_DAYS_PER_UNIT = {"day": 1, "week": 7, "month": 30}
_UNIT_NAME = {"day": "days", "week": "weeks", "month": "months"}

# "(±3 days)" | "(-3/+7 days)" | "(-3 to +7 d)" | "(window: ±2 wk)"
_WINDOW_RE = re.compile(
    r"[(\[]\s*(?:window\s*:?\s*)?"
    r"(?:-\s*(?P<sym_before>\d+)\s*/\s*\+\s*(?P<sym_after>\d+)"
    r"|±\s*(?P<pm>\d+)"
    r"|-\s*(?P<before>\d+)\s*(?:to|/|,)\s*\+?\s*(?P<after>\d+))"
    r"\s*(?P<unit>days?|d|weeks?|wks?)?\s*[)\]]",
    re.IGNORECASE)


@dataclass(frozen=True)
class TimePoint:
    text: str
    value: int
    unit: str          # "days" | "weeks" | "months"
    day_value: int      # normalized to days, for span/anchor comparisons


@dataclass(frozen=True)
class Window:
    before: int = 0
    after: int = 0
    unit: str = "days"

    @property
    def defined(self) -> bool:
        return bool(self.before or self.after)

    def as_dict(self) -> dict:
        return {"before": self.before, "after": self.after, "unit": self.unit}


def parse_timepoint(text: str, index: int) -> TimePoint:
    """A timing column's day value — same parse used since Phase 2, now shared
    with window/duration math. No match: falls back to the column's position."""
    m = _TIME_RE.search(text or "")
    if not m:
        return TimePoint(text=text or f"T{index}", value=index, unit="days", day_value=index)
    unit_key = m.group(1).lower()
    value = int(m.group(2))
    return TimePoint(text=text or f"T{index}", value=value, unit=_UNIT_NAME[unit_key],
                     day_value=value * _DAYS_PER_UNIT[unit_key])


def parse_window(text: str) -> Window:
    """A stated visit tolerance, or :class:`Window`'s all-zero default if none is found."""
    m = _WINDOW_RE.search(text or "")
    if not m:
        return Window()
    unit = "weeks" if (m.group("unit") or "d").lower().startswith("w") else "days"
    if m.group("pm"):
        n = int(m.group("pm"))
        return Window(before=n, after=n, unit=unit)
    if m.group("sym_before") is not None:
        return Window(before=int(m.group("sym_before")), after=int(m.group("sym_after")),
                      unit=unit)
    return Window(before=int(m.group("before")), after=int(m.group("after")), unit=unit)


def windows_for_columns(timings: list[str], visits: list[str]) -> list[dict]:
    """One :class:`Window` dict per visit column — never shorter than ``visits``.

    A column's own timing text is checked first, then its visit label (some
    SoAs annotate the tolerance next to the visit name instead of the day
    count). Columns with no stated tolerance get the all-zero window, which is
    what tells the assembler "no window" rather than "no answer" — see the
    module docstring.
    """
    out = []
    for i in range(len(visits)):
        w = parse_window(timings[i] if i < len(timings) else "")
        if not w.defined:
            w = parse_window(visits[i])
        out.append(w.as_dict())
    return out


def planned_duration_days(timings: list[str]) -> int | None:
    """Span, in days, from the earliest to the latest parsed timepoint.

    ``None`` for fewer than two timepoints or a zero span — a single-visit
    SoA, or one where nothing parsed, has nothing defensible to report.
    """
    if len(timings) < 2:
        return None
    days = [parse_timepoint(t, i).day_value for i, t in enumerate(timings)]
    span = max(days) - min(days)
    return span or None
