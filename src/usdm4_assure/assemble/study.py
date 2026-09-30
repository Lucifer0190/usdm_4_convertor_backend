"""Integrity E (full study) — assured metadata + design + SoA -> one USDM 4.0 study.

Composes a data4knowledge `AssemblerInput` and runs the top-level `Assembler`,
which orchestrates identification + document + population + design + timeline into
a complete, cross-referenced Study — then validates it.

This closes the loop: PDF -> C1 metadata + C2 design + SoA grid -> conformant USDM.
"""
from __future__ import annotations

from usdm4_assure.assemble.estimands import link_estimands
from usdm4_assure.assemble.fallback import assemble
from usdm4_assure.assemble.sanitize import sanitize
from usdm4_assure.assemble.soa import grid_to_timeline_input
from usdm4_assure.contracts import AssuredField, Finding
from usdm4_assure.extract.design import DesignExtract
from usdm4_assure.extract.eligibility import EligibilityExtract
from usdm4_assure.extract.estimands import EstimandsExtract
from usdm4_assure.extract.objectives import ObjectivesExtract
from usdm4_assure.extract.soa.grid import AssuredGrid
from usdm4_assure.validate.gate import validate_wrapper

# scope.standard keys usdm4's IdentificationAssembler recognises (STANDARD_ORGS); each
# maps a C6-extracted registry/regulatory field to the org usdm4 builds for it. A PIP
# number is an EMA decision number, so it is scoped to EMA like the EU CT number: that
# costs a DDF00174 *warning* (EMA holds two identifiers), where the generic "other"
# scope built an organisation of type "Unknown" and failed DDF00140/DDF00200 (errors).
_STANDARD_SCOPE = {"nct": "nct", "euCt": "ema", "eudract": "ema", "ind": "fda-ind", "pip": "ema"}


def _extra_identifiers(identifiers: dict[str, str | None]) -> list[dict]:
    """Registry/regulatory ``StudyIdentifier`` entries (task C-6), beyond the sponsor
    protocol identifier every study always carries at index 0.

    The compound code is deliberately *not* one of them: a second identifier scoped to
    the sponsor fails DDF00172 ("exactly one sponsor study identifier", an error). usdm4
    has a dedicated channel for it instead — see :func:`_compound_codes`.
    """
    out: list[dict] = []
    for field, standard in _STANDARD_SCOPE.items():
        value = identifiers.get(field)
        if value:
            out.append({"identifier": value, "scope": {"standard": standard}})
    return out


def _compound_codes(identifiers: dict[str, str | None]) -> str | None:
    """``identification.other.compound_codes``: usdm4 writes it as the StudyVersion's
    compound-codes extension (``CC_EXT_URL``), the model's own place for PF-codes."""
    compound = identifiers.get("compound")
    if not compound:
        return None
    return ", ".join(dict.fromkeys(c.strip() for c in compound.split(",") if c.strip()))


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
        texts = p.endpoints or ([p.endpoint] if p.endpoint else [])
        endpoints = [{"text": t, "level": p.level} for t in texts]
        items.append({"text": p.objective, "level": p.level, "endpoints": endpoints})
    return {"objectives": items, "estimands": []}


def _assembler_input(meta: dict, design: DesignExtract, ag: AssuredGrid,
                     elig: EligibilityExtract, objs: ObjectivesExtract,
                     estimands: EstimandsExtract | None = None,
                     identifiers: dict[str, str | None] | None = None,
                     ) -> tuple[dict, list[Finding]]:
    """The *raw* assembler input: extracted values only, ``None`` wherever
    extraction found nothing. :func:`usdm4_assure.assemble.sanitize.sanitize`
    is the one place those gaps are filled, each one reported as a finding."""
    version = meta.get("studyVersionIdentifier")
    interventions, arm_names = _interventions_from_arms(design)
    objectives, findings = link_estimands(estimands or EstimandsExtract(),
                                          _objectives_block(objs),
                                          [i["name"] for i in interventions])

    return {
        "identification": {
            "titles": {"brief": meta.get("studyAcronym"), "official": meta.get("studyTitle")},
            # The protocol identifier's organisation IS the sponsor in usdm4's model:
            # a non_standard organisation with role "sponsor" (``standard`` only takes
            # registry/regulator keys such as "nct" — "sponsor" there made the
            # assembler drop the identifier, the sponsor and its study role).
            "identifiers": [
                {"identifier": meta.get("protocolIdentifier"),
                 "scope": {"non_standard": {"type": None, "role": "sponsor",
                                            "name": meta.get("sponsorName"),
                                            "label": meta.get("sponsorName")}}}
            ] + _extra_identifiers(identifiers or {}),
            "other": {"compound_codes": _compound_codes(identifiers or {})},
        },
        "document": {
            "document": {"label": "Protocol", "version": version, "status": "final",
                         "template": "Sponsor", "version_date": None},
            "sections": None,
        },
        "population": {
            "label": None,
            "inclusion_exclusion": {"inclusion": list(elig.inclusion),
                                    "exclusion": list(elig.exclusion)},
            "demographics": {
                "age_min": elig.age_min, "age_max": elig.age_max,
                "age_unit": elig.age_unit, "sex": elig.sex,
                "healthy_volunteers": None,
            },
        },
        "study_design": {
            "label": None,
            "rationale": None,
            "trial_phase": meta.get("studyPhase"),
            "intervention_model": design.intervention_model,
            "arms": [{"name": a["name"], "type": a["type"],
                      "intervention_names": arm_names.get(a["name"], [])}
                     for a in design.arms],
            "interventions": interventions,
        },
        "study": {"name": None, "label": None, "version": version, "rationale": None},
        "objectives": objectives,
        "soa": grid_to_timeline_input(ag),
    }, findings


def build_full_study(assured_meta: list[AssuredField], design: DesignExtract,
                     ag: AssuredGrid, elig: EligibilityExtract | None = None,
                     objs: ObjectivesExtract | None = None,
                     run_core: bool = False,
                     estimands: EstimandsExtract | None = None,
                     amendments: dict | None = None,
                     sites: dict[str, str | None] | None = None,
                     identifiers: dict[str, str | None] | None = None) -> dict:
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
        sites: Extracted organization names (task 6.4,
            ``extract.sites.FIELDS``), attached after assembly since the
            assembler's own input schema cannot represent them.
        identifiers: Registry/regulatory/compound identifiers (task C-6,
            ``extract.identifiers.FIELDS``): NCT, EU CT/EudraCT, US IND, PIP,
            compound codes — added to ``identification.identifiers`` alongside
            the sponsor protocol identifier that is always present.

    Returns:
        A dict with keys ``ok`` (bool), ``wrapper`` (the USDM dict or ``None``),
        ``validation`` (gate report), ``assembler_errors`` (list[str]),
        ``summary`` (entity counts + resolved phase code), ``findings``
        (every sanitizer repair and assembly fallback step) and ``assembly``
        (which sections the assembler produced, fell back, or dropped, and
        the assembler reliance ratio).
    """
    elig = elig or EligibilityExtract()
    objs = objs or ObjectivesExtract()
    meta = {a.field: a.value for a in assured_meta if a.value}
    raw, findings = _assembler_input(meta, design, ag, elig, objs, estimands, identifiers)
    if amendments:
        raw["amendments"] = amendments
    data, repairs = sanitize(raw)
    findings = findings + repairs

    outcome = assemble(data, sites=sites)
    findings += outcome.findings
    if not outcome.study_ok:
        return {"ok": False, "assembler_errors": outcome.errors, "wrapper": None,
                "validation": None, "findings": findings, "assembly": outcome.report()}

    wdict = outcome.wrapper
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
            "assembler_errors": outcome.errors, "summary": summary, "findings": findings,
            "assembly": outcome.report()}
