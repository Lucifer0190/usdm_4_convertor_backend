"""Amendment-chain diff (task 6.2): two synthetic versions with known changes.

Version 2 changes the design (3 arms -> 2), raises the eligibility age limit,
and inserts a new section 5.2 that renumbers the old 5.2 to 5.3. Its amendment
summary explains the first two changes but not the new section. Every page
carries a footer with the version number, which must not register as a change.
"""
from __future__ import annotations

import pymupdf
import pytest

from usdm4_assure.assemble.amendments import amendment_input
from usdm4_assure.contracts import FindingKind, Severity
from usdm4_assure.extract.amendments import diff_pdfs, domains_touched

V1 = [
    [("CLINICAL STUDY PROTOCOL DA-301", 16)],
    [("4 STUDY DESIGN", 14), ("4.1 Overall Design", 13),
     (("Participants are randomized 1:1:1 to one of 3 arms: Drug A Low Dose, "
      "Drug A High Dose, or Placebo."), 9),
     ("4.2 End of Study Definition", 13),
     ("The study ends at the last visit of the last participant.", 9)],
    [("5 STUDY POPULATION", 14), ("5.1 Inclusion Criteria", 13),
     ("Adults aged 18 to 75 years at screening.", 9),
     ("5.2 Exclusion Criteria", 13), ("Pregnant or breastfeeding women.", 9)],
]
V2 = [
    [("CLINICAL STUDY PROTOCOL DA-301", 16),
     ("PROTOCOL AMENDMENT SUMMARY OF CHANGES", 14),
     (("Section 4.1 Overall Design: the low-dose arm was removed because interim "
      "pharmacokinetic data showed no exposure difference between doses."), 9),
     (("Section 5.1 Inclusion Criteria: the upper age limit was raised to widen "
      "recruitment."), 9)],
    [("4 STUDY DESIGN", 14), ("4.1 Overall Design", 13),
     ("Participants are randomized 1:1 to one of 2 arms: Drug A or Placebo.", 9),
     ("4.2 End of Study Definition", 13),
     ("The study ends at the last visit of the last participant.", 9)],
    [("5 STUDY POPULATION", 14), ("5.1 Inclusion Criteria", 13),
     ("Adults aged 18 to 80 years at screening.", 9),
     ("5.2 Lifestyle Considerations", 13),
     ("Participants must avoid grapefruit juice throughout the study.", 9),
     ("5.3 Exclusion Criteria", 13), ("Pregnant or breastfeeding women.", 9)],
]


def _pdf(path, pages, version: str):
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        y = 60
        for text, size in lines:
            page.insert_textbox(pymupdf.Rect(60, y, 550, y + 50), text, fontsize=size)
            y += 60
        page.insert_text((60, 780), f"Protocol DA-301 Version {version} Confidential", fontsize=8)
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(scope="module")
def diff(tmp_path_factory):
    d = tmp_path_factory.mktemp("amend")
    result, _old, _new = diff_pdfs(_pdf(d / "v1.pdf", V1, "1.0"), _pdf(d / "v2.pdf", V2, "2.0"))
    return result


def _by_title(diff):
    return {c.title: c for c in diff.changes}


def test_exactly_the_known_changes_are_found(diff):
    changes = _by_title(diff)
    assert set(changes) == {"Overall Design", "Inclusion Criteria", "Lifestyle Considerations"}
    assert changes["Overall Design"].kind == "modified"
    assert changes["Inclusion Criteria"].kind == "modified"
    assert changes["Lifestyle Considerations"].kind == "added"


def test_renumbering_and_version_footers_are_not_changes(diff):
    # "Exclusion Criteria" moved from 5.2 to 5.3 with identical text; every
    # footer differs ("Version 1.0" vs "2.0"); neither is a change.
    assert "Exclusion Criteria" not in _by_title(diff)
    assert "End of Study Definition" not in _by_title(diff)
    assert diff.unchanged >= 2


def test_description_spells_out_the_changed_words_and_is_grounded(diff):
    design = _by_title(diff)["Overall Design"]
    assert design.description == ("removed '1'; '3' -> '2'; "
                                  "removed 'Low Dose Drug A High Dose'")
    assert _by_title(diff)["Inclusion Criteria"].description == "'75' -> '80'"
    assert design.quote is not None and design.quote.ok and design.quote_version == "new"
    assert 0.0 < design.similarity < 1.0


def test_rationale_is_taken_from_the_amendment_summary_and_grounded(diff):
    design = _by_title(diff)["Overall Design"]
    assert "low-dose arm was removed" in design.rationale
    assert design.rationale_quote is not None and design.rationale_quote.ok
    assert "upper age limit" in _by_title(diff)["Inclusion Criteria"].rationale


def test_change_without_a_documented_rationale_is_reported(diff):
    added = _by_title(diff)["Lifestyle Considerations"]
    assert added.rationale == "" and added.rationale_quote is None
    assert any(f.kind is FindingKind.COMPLETENESS and "Lifestyle Considerations" in f.message
               for f in diff.findings)


def test_changes_are_attributed_to_extraction_domains(diff):
    changes = _by_title(diff)
    assert changes["Overall Design"].affected_domains == ("design",)
    assert changes["Inclusion Criteria"].affected_domains == ("eligibility",)
    assert domains_touched(diff)["eligibility"] == 2


# --- assembler input -------------------------------------------------------------------- #
def test_amendment_input_shape_and_honest_findings(diff):
    data, findings = amendment_input(diff, identifier="1")
    assert data["identifier"] == "1" and len(data["changes"]) == 3
    design = next(c for c in data["changes"] if c["section"] == "4.1, Overall Design")
    assert design["description"].startswith("Modified:")
    assert "low-dose arm" in design["rationale"]
    impact = next(f for f in findings if f.field == "impact")
    assert impact.severity is Severity.WARNING and "not assessed" in impact.message


def test_identical_versions_assemble_no_amendment(tmp_path):
    same, _o, _n = diff_pdfs(_pdf(tmp_path / "a.pdf", V1, "1.0"), _pdf(tmp_path / "b.pdf", V1, "1.0"))
    assert same.changes == []
    data, findings = amendment_input(same, identifier="1")
    assert data is None and "no amendment" in findings[0].message


def test_amendment_assembles_into_the_usdm_study(diff):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
    from make_full_fixture import build

    from usdm4_assure.assemble.study import build_full_study
    from usdm4_assure.extract.design import DesignExtract
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import extract_pdfplumber, extract_pymupdf

    pdf = build()
    grid = cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])
    design = DesignExtract(intervention_model="Parallel",
                           arms=[{"name": "Drug A", "type": "Experimental"},
                                 {"name": "Placebo", "type": "Placebo Comparator"}])
    data, _ = amendment_input(diff, identifier="1")
    study = build_full_study([], design, grid, amendments=data)
    assert study["ok"], study["assembler_errors"][:3]
    amendments = study["wrapper"]["study"]["versions"][0]["amendments"]
    assert len(amendments) == 1 and len(amendments[0]["changes"]) == 3
    design_change = next(c for c in amendments[0]["changes"]
                         if c["changedSections"] and
                         c["changedSections"][0]["sectionNumber"] == "4.1")
    assert "low-dose arm" in design_change["rationale"]


def test_run_full_with_previous_version_reports_the_amendment(tmp_path):
    import json

    from usdm4_assure.pipeline import run_full
    old, new = _pdf(tmp_path / "v1.pdf", V1, "1.0"), _pdf(tmp_path / "v2.pdf", V2, "2.0")
    result = run_full(new, out_dir=tmp_path / "out", previous_version=old,
                      amendment_identifier="1")
    assert {c.title for c in result.amendment_diff.changes} == {
        "Overall Design", "Inclusion Criteria", "Lifestyle Considerations"}
    review = json.loads((tmp_path / "out" / "review.json").read_text(encoding="utf-8"))
    assert any(f["domain"] == "amendments" and f["field"] == "impact"
               for f in review["findings"])
