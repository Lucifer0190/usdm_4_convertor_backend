"""Sanitizer (every repair is a finding) and per-section assembler fallback (task 6.3).

The fallback tests run the real usdm4 assembler on the full-protocol fixture's
input with one section deliberately broken at a time.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from usdm4_assure.assemble.fallback import assemble
from usdm4_assure.assemble.sanitize import STUDY_LABEL_MAX, sanitize
from usdm4_assure.assemble.study import _assembler_input
from usdm4_assure.contracts import FindingKind, Severity
from usdm4_assure.extract.design import DesignExtract
from usdm4_assure.extract.eligibility import EligibilityExtract
from usdm4_assure.extract.objectives import ObjectivePair, ObjectivesExtract

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
from make_full_fixture import build

META = {"studyTitle": "A Phase 2 Study of Drug A", "studyAcronym": "DA-2",
        "protocolIdentifier": "DA-201", "studyVersionIdentifier": "2.0",
        "sponsorName": "Drug A Pharma",
        "studyPhase": "Phase 2"}


@pytest.fixture(scope="module")
def grid():
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import extract_pdfplumber, extract_pymupdf
    pdf = build()
    return cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])


def _design(*names: str) -> DesignExtract:
    return DesignExtract(intervention_model="Parallel",
                         arms=[{"name": n, "type": "Experimental"} for n in names])


def _raw(grid, meta=META, design=None, elig=None, objs=None) -> dict:
    raw, _ = _assembler_input(
        meta, design or _design("Drug A", "Placebo"), grid,
        elig or EligibilityExtract(inclusion=["Adults."], exclusion=["Pregnancy."],
                                   age_min=18, age_max=75),
        objs or ObjectivesExtract(items=[ObjectivePair("Evaluate efficacy.", "PASI 75.",
                                                       "Primary")]))
    return raw


def _fields(findings, severity=None) -> set[str]:
    return {f.field for f in findings if severity is None or f.severity is severity}


# --- sanitizer ------------------------------------------------------------------------ #
def test_complete_input_reports_only_the_never_extracted_placeholders(grid):
    _, findings = sanitize(_raw(grid))
    assert all(f.kind is FindingKind.SANITIZER for f in findings)
    assert _fields(findings, Severity.ERROR) == set()
    assert {"versionDate", "documentSections", "healthyVolunteers"} <= _fields(
        findings, Severity.WARNING)


def test_never_extracted_fields_are_left_empty_not_invented(grid):
    """PLAN.md task C-8: a gap is reported and left empty, never filled with text that
    reads like a real answer."""
    raw = _raw(grid, meta={"studyTitle": "Study X"}, design=DesignExtract(arms=[]),
               elig=EligibilityExtract())
    clean, findings = sanitize(raw)
    assert {"protocolIdentifier", "studyPhase", "interventionModel", "inclusionCriteria",
            "exclusionCriteria"} <= _fields(findings, Severity.ERROR)
    assert clean["study_design"]["trial_phase"] == ""                    # not "Phase 1"
    assert clean["study_design"]["intervention_model"] == ""             # not "Parallel"
    assert clean["identification"]["identifiers"][0]["identifier"] == "" # not "SPONSOR-0000"
    assert clean["population"]["inclusion_exclusion"]["inclusion"] == [] # not a made-up criterion
    phase = next(f for f in findings if f.field == "studyPhase")
    assert "left empty" in phase.message and "Phase 1" not in phase.message
    assert phase.found is None                                          # nothing to grep for


def test_never_extracted_document_fields_carry_no_invented_text(grid):
    clean, findings = sanitize(_raw(grid, meta={k: v for k, v in META.items()
                                               if k != "studyVersionIdentifier"}))
    assert clean["document"]["document"]["version_date"] == ""   # not "2026-01-01"
    assert clean["document"]["sections"] == []                   # not a fake Synopsis section
    assert clean["study_design"]["rationale"] == ""               # not "Derived from ..."
    assert clean["study"]["rationale"] == ""                      # not "Assembled by ..."
    blob = str(clean)
    for invented in ("2026-01-01", "Synopsis extracted", "Derived from protocol synopsis",
                     "Assembled by USDM4-Assure", "Untitled Study", "SPONSOR-0000",
                     "Unknown Sponsor", "Adults >= 18 years"):
        assert invented not in blob
    assert {"versionDate", "documentSections"} <= _fields(findings, Severity.WARNING)


def test_missing_acronym_is_derived_and_reported(grid):
    clean, findings = sanitize(_raw(grid, meta={**META, "studyAcronym": None}))
    assert clean["identification"]["titles"]["brief"] == META["studyTitle"][:20]
    assert "studyAcronym" in _fields(findings, Severity.WARNING)
    assert clean["population"]["label"] == f"{META['studyTitle'][:20]} Population"


def test_duplicate_arm_names_are_renamed_consistently(grid):
    clean, findings = sanitize(_raw(grid, design=_design("Drug A", "Drug A", "Placebo")))
    design = clean["study_design"]
    assert [a["name"] for a in design["arms"]] == ["Drug A", "Drug A (2)", "Placebo"]
    assert design["arms"][1]["intervention_names"] == ["Drug A (2)"]
    assert [i["name"] for i in design["interventions"]] == ["Drug A", "Drug A (2)", "Placebo"]
    assert "arms" in _fields(findings, Severity.INFO)


def test_unnamed_arm_is_dropped_with_its_intervention(grid):
    clean, findings = sanitize(_raw(grid, design=_design("Drug A", "", "Placebo")))
    assert [a["name"] for a in clean["study_design"]["arms"]] == ["Drug A", "Placebo"]
    assert len(clean["study_design"]["interventions"]) == 2
    assert "arms" in _fields(findings, Severity.WARNING)


def test_empty_objective_dropped_and_dangling_estimand_removed(grid):
    raw = _raw(grid)
    raw["objectives"]["objectives"].append({"text": "", "level": "Secondary",
                                            "endpoints": [{"name": "END-9", "text": "X"}]})
    raw["objectives"]["estimands"] = [{"name": "EST-1", "summary_measure": "diff",
                                       "endpoint_name": "END-9"}]
    clean, findings = sanitize(raw)
    assert len(clean["objectives"]["objectives"]) == 1 and clean["objectives"]["estimands"] == []
    assert {"objectives", "estimands"} <= _fields(findings, Severity.WARNING)


def test_whitespace_normalized_and_long_label_truncated(grid):
    long_title = "A  Study\x0c of Drug A " + "x" * 200
    clean, findings = sanitize(_raw(grid, meta={**META, "studyTitle": long_title}))
    assert "\x0c" not in clean["identification"]["titles"]["official"]
    assert len(clean["study"]["label"]) == STUDY_LABEL_MAX
    infos = [f.message for f in findings if f.severity is Severity.INFO]
    assert any("normalized" in m for m in infos) and any("truncated" in m for m in infos)


def test_sanitize_never_mutates_its_input(grid):
    raw = _raw(grid, meta={"studyTitle": "Study X"})
    before = copy.deepcopy(raw)
    sanitize(raw)
    assert raw == before


# --- per-section fallback (real assembler) ----------------------------------------------- #
def _clean(grid, **kw) -> dict:
    return sanitize(_raw(grid, **kw))[0]


def test_clean_input_is_fully_assembler_produced(grid):
    out = assemble(_clean(grid))
    assert out.study_ok and out.attempts == 1 and out.dropped == []
    assert out.reliance_ratio == 1.0


def test_rejected_estimands_degrade_to_objectives_without_estimands(grid):
    data = _clean(grid)
    data["objectives"]["objectives"][0]["endpoints"][0]["name"] = "END-1"
    data["objectives"]["estimands"] = [{"name": "EST-1", "summary_measure": "diff",
                                        "endpoint_name": "END-1",
                                        "treatment_names": ["No Such Drug"]}]
    out = assemble(data)
    assert out.study_ok and out.attempts == 2 and out.dropped == []
    assert out.reliance_ratio == 1.0          # objectives still came from the assembler
    sd = out.wrapper["study"]["versions"][0]["studyDesigns"][0]
    assert len(sd["objectives"]) == 1 and sd["estimands"] == []
    assert any(f.field == "estimands" and f.severity is Severity.ERROR for f in out.findings)


def test_broken_soa_is_dropped_and_the_rest_salvaged(grid):
    data = _clean(grid)
    data["soa"] = {"epochs": "not a table"}
    out = assemble(data)
    assert out.study_ok and "soa" in out.dropped
    assert out.reliance_ratio == pytest.approx(6 / 7)
    assert any(f.field == "soa" and f.severity is Severity.ERROR for f in out.findings)


def test_broken_objectives_are_rebuilt_by_the_builder_fallback(grid):
    data = _clean(grid)
    data["objectives"]["objectives"].append({"level": "Secondary"})   # no text: schema error
    out = assemble(data)
    assert out.study_ok and "objectives" in out.dropped
    assert out.fallback_sections == ["objectives"]
    assert "objectives" not in out.assembler_sections       # fallback doesn't count as reliance
    sd = out.wrapper["study"]["versions"][0]["studyDesigns"][0]
    assert [o["text"] for o in sd["objectives"]] == ["Evaluate efficacy."]
    assert sd["objectives"][0]["level"]["decode"]              # coded like the assembler does
    assert any("could not rebuild objective 2" in f.message for f in out.findings)


def test_required_section_failure_has_no_fallback(grid):
    data = _clean(grid)
    data["identification"] = {"titles": "not a mapping"}
    out = assemble(data)
    assert not out.study_ok and out.wrapper is None
    assert any("required section" in f.message for f in out.findings)


def test_sponsor_is_scoped_as_a_sponsor_organisation(grid):
    # Regression: scope {"standard": "sponsor"} made the assembler silently drop
    # the protocol identifier, the sponsor organisation and its study role.
    out = assemble(_clean(grid))
    assert out.errors == []
    sv = out.wrapper["study"]["versions"][0]
    org = sv["organizations"][0]
    assert org["name"] == "Drug A Pharma" and org["type"]["decode"] == "Unknown"
    assert sv["studyIdentifiers"][0]["scopeId"] == org["id"]
    assert [r["code"]["decode"] for r in sv["roles"]] == ["Clinical Study Sponsor"]


def test_missing_sponsor_name_is_flagged_and_gets_the_one_required_sentinel(grid):
    clean, findings = sanitize(_raw(grid, meta={k: v for k, v in META.items()
                                               if k != "sponsorName"}))
    assert "sponsorName" in _fields(findings, Severity.ERROR)
    org = clean["identification"]["identifiers"][0]["scope"]["non_standard"]
    # usdm4's Organization.name cannot be empty (Field(min_length=1)): this is the one
    # field the sentinel is used for, and it is unmistakably synthetic, not fabricated data.
    assert org["name"] == "[not extracted]"
    assert org["label"] == ""                # label has no such constraint: stays empty
    assert org["type"] == "unknown"           # a CDISC code, not a fabricated fact


def test_nothing_extracted_at_all_still_assembles(grid):
    """The extreme case task C-8 has to survive: title, sponsor, protocol id, phase and
    intervention model are all missing at once. usdm4's Study.name and Organization.name
    still get their one sentinel; everything else stays empty and the assembler succeeds."""
    from usdm4_assure.assemble.fallback import assemble

    raw = _raw(grid, meta={}, design=DesignExtract(arms=[]), elig=EligibilityExtract())
    clean, findings = sanitize(raw)
    assert clean["study"]["name"] == {"acronym": "[not extracted]"}
    assert clean["study_design"]["trial_phase"] == ""
    out = assemble(clean)
    assert out.study_ok, out.errors
    sv = out.wrapper["study"]["versions"][0]
    assert sv["organizations"][0]["name"] == "[not extracted]"
    assert {"studyTitle", "sponsorName", "protocolIdentifier"} <= _fields(
        findings, Severity.ERROR)


def test_syntax_template_text_is_xml_escaped_for_ddf00247(grid):
    raw = _raw(grid, elig=EligibilityExtract(inclusion=["ANC <1500/mm3 & platelets >100."],
                                             exclusion=["Pregnancy."], age_min=18, age_max=75),
               objs=ObjectivesExtract(items=[ObjectivePair("Evaluate RNA <LLOQ.",
                                                           "Time to RNA <LLOQ.", "Primary")]))
    clean, findings = sanitize(raw)
    assert clean["population"]["inclusion_exclusion"]["inclusion"] == [
        "ANC &lt;1500/mm3 &amp; platelets &gt;100."]
    obj = clean["objectives"]["objectives"][0]
    assert obj["text"] == "Evaluate RNA &lt;LLOQ." and obj["endpoints"][0]["text"] == \
        "Time to RNA &lt;LLOQ."
    assert any("DDF00247" in f.message for f in findings)
    out = assemble(clean)
    from usdm4_assure.validate.gate import validate_wrapper
    assert "DDF00247" not in validate_wrapper(out.wrapper)["d4k"]["failed_rules"]
