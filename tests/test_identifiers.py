"""Registry/regulatory/compound identifiers (task C-6): deterministic label parser
over the title-page block every sampled Pfizer protocol carries."""
from __future__ import annotations

import pymupdf
import pytest

from usdm4_assure.extract.identifiers import FIELDS, extract_identifiers, extract_labels
from usdm4_assure.ingest.pdf import ingest

LINES = [
    "Study Intervention Number: PF-07850327, Abemaciclib",
    "US IND Number: 162074",
    "EU CT Number: 2022-502228-34-00",
    "ClinicalTrials.gov ID: NCT05548127",
    "Protocol Number: C4891006",
    "Pediatric Investigational Plan Number: Not Applicable",
]


def _pdf(tmp_path, lines):
    path = tmp_path / "protocol.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for line in lines:
        page.insert_textbox(pymupdf.Rect(50, y, 550, y + 30), line, fontsize=10)
        y += 30
    doc.save(str(path))
    doc.close()
    return ingest(path)


@pytest.fixture()
def doc(tmp_path):
    return _pdf(tmp_path, LINES)


def test_each_label_produces_a_grounded_candidate(doc):
    cands = {c.field: c for c in extract_labels(doc)}
    assert cands["ind"].value == "162074"
    assert cands["euCt"].value == "2022-502228-34-00"
    assert cands["nct"].value == "NCT05548127"
    assert all(c.quote is not None for c in cands.values())


def test_a_combination_therapy_line_keeps_only_the_pfizer_compound_code(doc):
    cands = {c.field: c for c in extract_labels(doc)}
    assert cands["compound"].value == "PF-07850327"          # not ", Abemaciclib"


def test_placeholder_values_produce_no_candidate(doc):
    fields = {c.field for c in extract_labels(doc)}
    assert "pip" not in fields                                 # "Not Applicable"


@pytest.mark.parametrize("value", ["Not Available", "N/A", "TBD", "Unknown", "NA"])
def test_every_not_a_value_spelling_is_filtered(tmp_path, value):
    doc = _pdf(tmp_path, [f"ClinicalTrials.gov ID: {value}"])
    assert extract_identifiers(doc) == []


def test_multiple_compound_codes_are_kept_and_deduplicated(tmp_path):
    doc = _pdf(tmp_path, ["Study Intervention Number: PF-06651600 and PF-06651600 (combo)"])
    cands = extract_labels(doc)
    assert cands[0].value == "PF-06651600"


def test_a_page_with_no_label_block_yields_nothing(tmp_path):
    doc = _pdf(tmp_path, ["A Study of Nothing in Particular"])
    assert extract_identifiers(doc) == []


def test_labels_past_the_front_matter_are_ignored(tmp_path):
    path = tmp_path / "p.pdf"
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.new_page()
    pdf.new_page().insert_textbox(pymupdf.Rect(50, 60, 550, 90),
                                  "ClinicalTrials.gov ID: NCT99999999", fontsize=10)
    pdf.save(str(path))
    pdf.close()
    assert extract_identifiers(ingest(path)) == []


def test_fields_list_matches_the_labels():
    assert set(FIELDS) == {"nct", "euCt", "eudract", "ind", "pip", "compound"}


# --- assembly: the extra identifiers actually reach the delivered USDM ------------------ #
def test_extracted_identifiers_become_extra_study_identifiers():
    from usdm4_assure.assemble.study import _compound_codes, _extra_identifiers

    ids = {"nct": "NCT05548127", "euCt": "2022-502228-34-00", "ind": "162074",
           "pip": "EMA/PE/0000229195", "compound": "PF-07850327, PF-07850327"}
    by_value = {e["identifier"]: e["scope"] for e in _extra_identifiers(ids)}
    assert by_value == {"NCT05548127": {"standard": "nct"},
                        "2022-502228-34-00": {"standard": "ema"},
                        "162074": {"standard": "fda-ind"},
                        "EMA/PE/0000229195": {"standard": "ema"}}   # PIP: an EMA number
    # The compound code is not a StudyIdentifier (a second sponsor-scoped identifier fails
    # DDF00172); it goes to usdm4's compound-codes channel, de-duplicated.
    assert "PF-07850327" not in by_value
    assert _compound_codes(ids) == "PF-07850327"


def test_no_identifiers_extracted_means_no_extra_entries():
    from usdm4_assure.assemble.study import _compound_codes, _extra_identifiers

    assert _extra_identifiers({}) == []
    assert _extra_identifiers({"nct": None, "pip": ""}) == []
    assert _compound_codes({}) is None


def test_identifiers_flow_through_a_real_assembly():
    """End-to-end: extracted identifiers reach the delivered USDM's studyIdentifiers,
    through the real usdm4 assembler (not just the raw input dict)."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
    from make_full_fixture import build

    from usdm4_assure.assemble.study import build_full_study
    from usdm4_assure.contracts import AssuredField, Decision
    from usdm4_assure.extract.design import DesignExtract
    from usdm4_assure.extract.eligibility import EligibilityExtract
    from usdm4_assure.extract.objectives import ObjectivePair, ObjectivesExtract
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import extract_pdfplumber, extract_pymupdf

    pdf = build()
    grid = cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])
    meta = [AssuredField(field=k, value=v, candidates=[], methods_agree=True, n_methods=1,
                         verifier="n/a", confidence=1.0, decision=Decision.AUTO_ACCEPT)
           for k, v in {"studyTitle": "A Phase 2 Study of Drug A", "studyAcronym": "DA-2",
                        "protocolIdentifier": "DA-201", "studyVersionIdentifier": "2.0",
                        "sponsorName": "Drug A Pharma", "studyPhase": "Phase 2"}.items()]
    design = DesignExtract(intervention_model="Parallel",
                           arms=[{"name": "Drug A", "type": "Experimental"},
                                 {"name": "Placebo", "type": "Placebo"}])
    elig = EligibilityExtract(inclusion=["Adults."], exclusion=["Pregnancy."],
                              age_min=18, age_max=75)
    objs = ObjectivesExtract(items=[ObjectivePair("Evaluate efficacy.", "PASI 75.", "Primary")])
    out = build_full_study(
        meta, design, grid, elig, objs,
        identifiers={"nct": "NCT12345678", "euCt": "2022-500000-11-00", "compound": "PF-00000001"})
    assert out["ok"], out["assembler_errors"]
    sv = out["wrapper"]["study"]["versions"][0]
    ids = {i["text"] for i in sv["studyIdentifiers"]}
    assert {"DA-201", "NCT12345678", "2022-500000-11-00"} <= ids
    assert "PF-00000001" not in ids                          # not a second sponsor identifier
    ext = {e["url"]: e.get("valueString") for e in sv.get("extensionAttributes", [])}
    assert ext.get("www.d4k.dk/usdm/extensions/004") == "PF-00000001"   # compound codes

    from usdm4_assure.eval.rubric import view_of
    assert "PF-00000001" in view_of(out["wrapper"])["identifiers"]   # still scored as extracted

    from usdm4_assure.validate.gate import validate_wrapper
    failed = validate_wrapper(out["wrapper"])["d4k"]["failed_rules"]
    assert "DDF00172" not in failed and "DDF00174" not in failed
