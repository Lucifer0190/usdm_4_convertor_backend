"""Integrity E (SoA) — assured grid -> valid USDM ScheduleTimeline entities.

Uses the data4knowledge `TimelineAssembler`, which mints conformant Encounter /
StudyEpoch / Activity / ScheduledActivityInstance / Timing / Condition objects
(with proper cross-references and CDISC Codes from the bundled CT cache — no API
key needed) from a structured SoA description.

We build that structured description from our AssuredGrid, so the pipeline is:
    PDF -> extract (2 methods) -> cross-validate -> THIS -> USDM SoA entities.

Wrapping these in a full StudyDesign (arms / population / cells) belongs to the
design-skeleton domain (C2) and is intentionally out of scope here.
"""
from __future__ import annotations

import os

from usdm4_assure.extract.soa.grid import AssuredGrid
from usdm4_assure.soa.timing import parse_timepoint, planned_duration_days, windows_for_columns


def _parse_timepoint(text: str, index: int) -> dict:
    tp = parse_timepoint(text, index)
    return {"index": str(index), "text": tp.text, "value": str(tp.value), "unit": tp.unit}


def grid_to_timeline_input(ag: AssuredGrid) -> dict:
    """Map an :class:`AssuredGrid` to the ``TimelineAssembler`` input schema.

    Footnote-gated activities are given letter markers (``a``, ``b`` …) and a
    matching ``ConditionItem`` so the assembler emits USDM ``Condition`` objects.

    Args:
        ag: The cross-validated Schedule of Activities grid.

    Returns:
        A ``TimelineInput``-shaped dict (``epochs``/``visits``/``timepoints``/
        ``activities``/``conditions`` blocks) ready for the assembler.
    """
    # footnote marker per gated activity: assign 'a', 'b', ...
    gated = list(ag.footnote_activities)
    marker = {name: chr(ord("a") + i) for i, name in enumerate(gated)}

    epochs = {"found": True, "items": [{"text": e} for e in ag.epochs]}
    visits = {"found": True,
              "items": [{"text": v, "references": []} for v in ag.visits]}
    timepoints = {"found": True,
                  "items": [_parse_timepoint(t, i) for i, t in enumerate(ag.timings)]}
    # One Window per visit column, never an empty list — see soa.timing's
    # module docstring for why an empty windows.items breaks DDF00006/DDF00025.
    window_items = windows_for_columns(ag.timings, ag.visits)
    windows = {"found": any(w["before"] or w["after"] for w in window_items),
              "items": window_items}

    # activities: for each row, the visit indices where a present cell exists
    present_by_act: dict[int, list[int]] = {}
    for c in ag.present_cells():
        present_by_act.setdefault(c.activity_i, []).append(c.visit_i)

    activity_items = []
    conditions = []
    for ai, name in enumerate(ag.activities):
        refs = [marker[name]] if name in marker else []
        vis = [{"index": vi, "references": refs}
               for vi in sorted(present_by_act.get(ai, []))]
        # DDF00075 ("an activity should reference a procedure/BC/BC-surrogate")
        # is deliberately NOT addressed by populating actions.bcs here. Tried
        # it: offering the activity's own name as a "bc" does get a genuine
        # exact-name match sometimes (e.g. "Informed Consent" against the
        # bundled CDISC BC library) — but TimelineAssembler._get_biomedical_
        # concepts() also mints a Procedure for *every* bc name with a
        # hardcoded placeholder Code("12345", "LOINC") whose decode is the bc
        # name, so every activity's Procedure shares the same fake code with a
        # different decode. That trips DDF00035 (non-1:1 code/decode) with a
        # fabricated LOINC code — worse than the WARNING it would silence.
        # DDF00075 stays a documented known gap (validate/repair.py).
        activity_items.append({"name": name, "visits": vis, "references": refs})
        if name in marker:
            conditions.append({"reference": marker[name],
                               "text": f"{name} is footnote-gated ({marker[name]})."})

    return {
        "table_type": "main_soa",
        "epochs": epochs,
        "visits": visits,
        "timepoints": timepoints,
        "windows": windows,
        "activities": {"found": True, "items": activity_items},
        "conditions": {"found": bool(conditions), "items": conditions},
    }


def repair_timeline(builder, timelines: list, encounters: list, epochs: list) -> list[str]:
    """Post-assembly SoA fixups the assembler's own input schema has no field for.

    * ``ScheduleTimeline.plannedDuration`` is hardcoded to ``None`` in
      ``TimelineAssembler`` — there is no input field for it — so DDF00153
      can only be satisfied by setting it directly on the assembled object.
    * ``Encounter``/``StudyEpoch`` are never ``double_link``-ed by
      ``TimelineAssembler`` (only ``Activity`` is), which fails DDF00087/DDF00088.
      Both are pure linked-list bookkeeping over objects already built
      correctly — fixable here without new extraction (conformance.md Bucket 3).

    Args:
        builder: The assembler's own ``Builder`` (for ``double_link``), so
            this reuses whatever CT/id state the study was built with rather
            than constructing a new one.
        timelines: The assembled ``ScheduleTimeline`` list.
        encounters: The assembled ``Encounter`` list.
        epochs: The assembled ``StudyEpoch`` list.

    Returns:
        Human-readable notes on what was repaired, for the caller to fold
        into its own findings.
    """
    notes = []
    for tl in timelines:
        if not tl.mainTimeline or tl.plannedDuration is not None:
            continue
        days = planned_duration_days([_parse_timepoint_text(t) for t in tl.timings])
        if days is None:
            continue
        duration = _build_duration(builder, days)
        if duration is None:
            continue
        tl.plannedDuration = duration
        notes.append(f"plannedDuration set to {days} day(s) from the timeline's own timings "
                     "(the assembler never populates this field).")
    for name, items in (("encounters", encounters), ("epochs", epochs)):
        # double_link() is a pure, deterministic re-derivation from list
        # order — safe (and cheap) to always apply, not just on first sight.
        if items:
            builder.double_link(items, "previousId", "nextId")
            notes.append(f"{name}: previousId/nextId linked (never set by the assembler).")
    return notes


def _parse_timepoint_text(timing) -> str:
    """A ``Timing``'s own ``valueLabel`` (the timepoint text it was built
    from), so :func:`repair_timeline` re-derives duration from the same
    source the assembler used, not from a grid the caller may not have."""
    return getattr(timing, "valueLabel", "") or ""


def _build_duration(builder, days: int):
    """A real ``Duration`` (days, as a coded ``Quantity``) via the assembler's
    own builder — not a bare string; ``ScheduleTimeline.plannedDuration`` is
    typed ``Duration | None``."""
    from usdm4.api.duration import Duration
    from usdm4.api.quantity_range import Quantity

    unit_code = builder.cdisc_unit_code("days")
    quantity = builder.create(Quantity, {
        "value": float(days),
        "unit": builder.alias_code(unit_code) if unit_code else None,
    })
    return builder.create(Duration, {
        "text": f"{days} day(s)", "quantity": quantity, "durationWillVary": False,
    })


def build_soa(ag: AssuredGrid) -> dict:
    """Run the TimelineAssembler; return the assembled USDM SoA entities + summary."""
    import usdm4
    from simple_error_log.errors import Errors
    from usdm4.assembler.timeline_assembler import TimelineAssembler
    from usdm4.builder.builder import Builder

    root = os.path.dirname(usdm4.__file__)
    builder = Builder(root, Errors())
    errors = Errors()
    ta = TimelineAssembler(builder, errors)
    ta.execute(grid_to_timeline_input(ag))

    timelines = ta.timelines
    sais = timelines[0].instances if timelines else []
    encounters = ta.encounters
    activities = ta.activities
    repair_notes = repair_timeline(builder, timelines, encounters, ta.epochs)

    # SAI per encounter -> activityIds. Verify by mapping ids back to names.
    act_name = {a.id: (getattr(a, "label", None) or a.name) for a in activities}
    enc_name = {e.id: (e.label or e.name) for e in encounters}
    sai_map = {}
    for sai in sais:
        enc = enc_name.get(getattr(sai, "encounterId", None), getattr(sai, "name", "?"))
        sai_map[enc] = [act_name.get(i, i) for i in getattr(sai, "activityIds", [])]

    return {
        "entities": {
            "epochs": ta.epochs, "encounters": encounters,
            "activities": activities, "timelines": timelines,
            "conditions": ta.conditions,
        },
        "summary": {
            "epochs": len(ta.epochs), "encounters": len(encounters),
            "activities": len(activities),
            "scheduled_instances": len(sais),
            "conditions": len(ta.conditions),
            "timings": len(timelines[0].timings) if timelines else 0,
        },
        "sai_activities_by_encounter": sai_map,
        "assembler_errors": [str(e.get("message", e)) for e in errors.to_dict()],
        "repair_notes": repair_notes,
    }
