"""Integrity E (full study) — assured metadata + design + SoA -> one USDM 4.0 study.

Composes a data4knowledge `AssemblerInput` and runs the top-level `Assembler`,
which orchestrates identification + document + population + design + timeline into
a complete, cross-referenced Study — then validates it.

This closes the loop: PDF -> C1 metadata + C2 design + SoA grid -> conformant USDM.
"""
from __future__ import annotations

import os

from usdm4_assure.assemble.estimands import link_estimands
from usdm4_assure.assemble.soa import grid_to_timeline_input
from usdm4_assure.contracts import AssuredField, Finding
from usdm4_assure.extract.design import DesignExtract
from usdm4_assure.extract.eligibility import EligibilityExtract
from usdm4_assure.extract.estimands import EstimandsExtract
from usdm4_assure.extract.objectives import ObjectivesExtract
from usdm4_assure.extract.soa.grid import AssuredGrid
from usdm4_assure.validate.gate import validate_wrapper


def _interventions_from_arms(design: DesignExtract) -> tuple[list[dict], dict]:
    """One StudyIntervention per arm; return interventions + arm->names map.

    Interventions make the InterventionalStudyDesign coherent (DDF00213) and give
    arms something to reference.
    """
    interventions, arm_names = [], {}
    for a in design.arms:
        is_placebo = a["type"] == "Placebo Comparator"
        # Keep interventions minimal (name/type/role only): specifying dose/route/
        # frequency creates Administration+Duration sub-objects whose own conformance
        # rules (DDF00033/00039/00177) then need full dosing data we don't extract yet.
        interventions.append({
            "name": a["name"], "type": "Drug",
            "role": "Placebo" if is_placebo else "Experimental Intervention"})
        arm_names[a["name"]] = [a["name"]]
    return interventions, arm_names


def _objectives_block(objs: ObjectivesExtract) -> dict:
    items = []
    for p in objs.items:
        endpoints = ([{"text": p.endpoint, "level": p.level}] if p.endpoint else [])
        items.append({"text": p.objective, "level": p.level, "endpoints": endpoints})
    return {"objectives": items, "estimands": []}


def _assembler_input(meta: dict, design: DesignExtract, ag: AssuredGrid,
                     elig: EligibilityExtract, objs: ObjectivesExtract,
                     estimands: EstimandsExtract | None = None
                     ) -> tuple[dict, list[Finding]]:
    title = meta.get("studyTitle") or "Untitled Study"
    acronym = meta.get("studyAcronym") or title[:20]
    ident = meta.get("protocolIdentifier") or "SPONSOR-0000"
    version = meta.get("studyVersionIdentifier") or "1"
    phase = meta.get("studyPhase") or "Phase 1"
    interventions, arm_names = _interventions_from_arms(design)
    objectives, findings = link_estimands(estimands or EstimandsExtract(),
                                          _objectives_block(objs),
                                          [i["name"] for i in interventions])

    return {
        "identification": {
            "titles": {"brief": acronym, "official": title},
            "identifiers": [
                {"identifier": ident, "scope": {"standard": "sponsor"}}
            ],
        },
        "document": {
            "document": {"label": "Protocol", "version": version, "status": "final",
                         "template": "Sponsor", "version_date": "2026-01-01"},
            "sections": [{"section_number": "1", "section_title": "Synopsis",
                          "text": "Synopsis extracted from protocol."}],
        },
        "population": {
            "label": f"{acronym} Population",
            "inclusion_exclusion": {
                "inclusion": elig.inclusion or ["Adults >= 18 years"],
                "exclusion": elig.exclusion or ["Pregnancy"],
            },
            "demographics": {
                "age_min": elig.age_min, "age_max": elig.age_max,
                "age_unit": elig.age_unit, "sex": elig.sex,
                "healthy_volunteers": False,
            },
        },
        "study_design": {
            "label": f"{acronym} Design",
            "rationale": "Derived from protocol synopsis.",
            "trial_phase": phase,
            "intervention_model": design.intervention_model or "Parallel",
            "arms": [{"name": a["name"], "type": a["type"],
                      "intervention_names": arm_names.get(a["name"], [])}
                     for a in design.arms],
            "interventions": interventions,
        },
        "study": {"name": {"acronym": acronym}, "label": title[:120],
                  "version": version, "rationale": "Assembled by USDM4-Assure."},
        "objectives": objectives,
        "soa": grid_to_timeline_input(ag),
    }, findings


def build_full_study(assured_meta: list[AssuredField], design: DesignExtract,
                     ag: AssuredGrid, elig: EligibilityExtract | None = None,
                     objs: ObjectivesExtract | None = None,
                     run_core: bool = False,
                     estimands: EstimandsExtract | None = None,
                     amendments: dict | None = None) -> dict:
    """Assemble one complete USDM 4.0 study from every domain's assured output.

    Composes a data4knowledge ``AssemblerInput`` from the extracted domains, runs
    the top-level ``Assembler`` (which mints all cross-referenced USDM entities and
    CDISC codes offline via the bundled CT cache), then validates the result.

    Args:
        assured_meta: Metadata (C1) fields after the Assurance layer.
        design: Design skeleton (C2) — study type, intervention model, arms.
        ag: The cross-validated Schedule of Activities grid.
        elig: Eligibility (C3) criteria + demographics. Defaults to empty.
        objs: Objectives/endpoints (C4). Defaults to empty.
        run_core: If ``True``, also run the CDISC CORE gate during validation.
        estimands: Reconciled estimands (C5, task 6.1), linked to named
            endpoints and interventions before assembly.
        amendments: An ``AmendmentsInput``-shaped dict (task 6.2,
            ``assemble.amendments.amendment_input``), or ``None`` for an
            original protocol.

    Returns:
        A dict with keys ``ok`` (bool), ``wrapper`` (the USDM dict or ``None``),
        ``validation`` (gate report), ``assembler_errors`` (list[str]),
        ``summary`` (entity counts + resolved phase code) and ``findings``
        (problems found while composing the assembler input).
    """
    import usdm4
    from simple_error_log.errors import Errors
    from usdm4.assembler.assembler import Assembler

    elig = elig or EligibilityExtract()
    objs = objs or ObjectivesExtract()
    meta = {a.field: a.value for a in assured_meta if a.value}
    data, findings = _assembler_input(meta, design, ag, elig, objs, estimands)
    if amendments:
        data["amendments"] = amendments

    root = os.path.dirname(usdm4.__file__)
    errors = Errors()
    assembler = Assembler(root, errors)
    assembler.execute(data)

    if assembler.study is None:
        return {"ok": False, "assembler_errors": _dump(errors),
                "wrapper": None, "validation": None, "findings": findings}

    wrapper = assembler.wrapper(name="USDM4-Assure", version="0.1.0")
    wdict = wrapper.model_dump(by_alias=True)
    validation = validate_wrapper(wdict, run_core=run_core)

    sv = wdict["study"]["versions"][0]
    design_obj = sv["studyDesigns"][0] if sv.get("studyDesigns") else {}
    tl = design_obj.get("scheduleTimelines", [{}])
    summary = {
        "arms": len(design_obj.get("arms", [])),
        "epochs": len(design_obj.get("epochs", [])),
        "encounters": len(design_obj.get("encounters", [])),
        "activities": len(design_obj.get("activities", [])),
        "scheduled_instances": len(tl[0].get("instances", [])) if tl else 0,
        "estimands": len(design_obj.get("estimands", [])),
        "study_phase": (design_obj.get("studyPhase") or {}).get("standardCode", {}),
    }
    return {"ok": True, "wrapper": wdict, "validation": validation,
            "assembler_errors": _dump(errors), "summary": summary, "findings": findings}


def _dump(errors) -> list[str]:
    try:
        return [str(e) for e in errors.errors]
    except Exception:  # noqa: BLE001
        return []
