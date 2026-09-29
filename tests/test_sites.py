"""Organizations and study roles (task 6.4): deterministic + grounded LLM member,
builder-fallback assembly."""
from __future__ import annotations

import json

import pymupdf
import pytest

from usdm4_assure.assemble.sites import ORG_TYPE_CODES, ROLE_CODES, attach_organizations
from usdm4_assure.contracts import Decision, Method
from usdm4_assure.extract.sites import FIELDS, extract_labels, extract_llm_grounded, extract_sites
from usdm4_assure.ingest.pdf import ingest

LINES = [
    "Clinical Study Protocol",
    "Sponsor: Northwind Therapeutics, Inc.",
    "Contract Research Organization: Acme Clinical Research CRO",
    "Central Laboratory: Precision Diagnostics Central Lab",
    "5 STUDY ASSESSMENTS",
    "5.1 Laboratory Assessments",
    "Local laboratory results will be used for safety monitoring.",
]


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    path = tmp_path_factory.mktemp("sites") / "protocol.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    y = 60
    for line in LINES:
        page.insert_textbox(pymupdf.Rect(50, y, 550, y + 40), line, fontsize=10)
        y += 45
    pdf.save(path)
    pdf.close()
    return ingest(path)


class _StubLLM:
    available = True
    name = "route"
    model = "anthropic/claude-sonnet-4.5"

    def __init__(self, items):
        self._items = items

    def complete(self, prompt, *, task="extract_prose", system=None, max_tokens=1024):
        return "reasoning" if "YOUR REASONING" not in prompt else json.dumps(self._items)


# --- deterministic member ------------------------------------------------------------ #
def test_extract_labels_finds_cro_and_lab(doc):
    cands = extract_labels(doc)
    values = {c.field: c.value for c in cands}
    assert values == {"croName": "Acme Clinical Research CRO",
                      "centralLaboratoryName": "Precision Diagnostics Central Lab"}
    assert all(c.method is Method.DET_TEXT and c.quote.ok for c in cands)


def test_extract_labels_does_not_fire_on_unrelated_laboratory_heading(doc):
    # "5.1 Laboratory Assessments" and "Local laboratory results..." must not
    # be mistaken for a "Central Laboratory:" label.
    cands = extract_labels(doc)
    assert len(cands) == 2


def test_extract_labels_finds_nothing_without_the_labels():
    from pathlib import Path

    from usdm4_assure.contracts import Document
    empty = Document(source=Path("x.pdf"), blocks=[], full_text="")
    assert extract_labels(empty) == []


# --- LLM member --------------------------------------------------------------------- #
def test_llm_member_grounds_both_fields(doc):
    llm = _StubLLM([
        {"field": "croName", "value": "Acme Clinical Research CRO",
         "quote": "Contract Research Organization: Acme Clinical Research CRO"},
        {"field": "centralLaboratoryName", "value": "Precision Diagnostics Central Lab",
         "quote": "Central Laboratory: Precision Diagnostics Central Lab"},
    ])
    cands = extract_llm_grounded(doc, llm)
    assert len(cands) == 2
    assert all(c.method is Method.LLM_FRONTIER and c.quote.ok and c.prompt_hash for c in cands)


def test_llm_member_unavailable_returns_nothing(doc):
    class Down:
        available = False
    assert extract_llm_grounded(doc, Down()) == []


def test_llm_hallucinated_quote_fails_grounding(doc):
    llm = _StubLLM([{"field": "croName", "value": "Fabricated CRO Name",
                     "quote": "this text is not in the document"}])
    (cand,) = extract_llm_grounded(doc, llm)
    assert not cand.quote.ok


# --- combined extraction -------------------------------------------------------------- #
def test_extract_sites_combines_both_members(doc):
    llm = _StubLLM([{"field": "croName", "value": "Acme Clinical Research CRO",
                     "quote": "Contract Research Organization: Acme Clinical Research CRO"}])
    cands = extract_sites(doc, llm)
    assert len(cands) == 3   # 2 deterministic + 1 LLM (agreeing on croName)


def test_extract_sites_without_an_llm_member(doc):
    assert len(extract_sites(doc)) == 2


def test_fields_constant_matches_org_type_mapping():
    assert set(FIELDS) == {"croName", "centralLaboratoryName"}


# --- assembly: builder fallback (real usdm4 assembler) ------------------------------------ #
class _FakeStudy:
    def __init__(self, versions):
        self.versions = versions


class _FakeVersion:
    def __init__(self):
        self.organizations = []
        self.roles = []


class _FakeAsm:
    def __init__(self, builder):
        self.study = _FakeStudy([_FakeVersion()])
        self._builder = builder


@pytest.fixture
def real_builder():
    import os

    import usdm4
    from simple_error_log.errors import Errors
    from usdm4.builder.builder import Builder
    return Builder(os.path.dirname(usdm4.__file__), Errors())


def test_attach_organizations_creates_org_and_role_for_lab(real_builder):
    asm = _FakeAsm(real_builder)
    findings = attach_organizations(asm, {"centralLaboratoryName": "Precision Diagnostics"})
    version = asm.study.versions[0]
    assert len(version.organizations) == 1
    org = version.organizations[0]
    assert org.name == "Precision Diagnostics"
    assert org.type.code == ORG_TYPE_CODES["lab"][0]
    assert len(version.roles) == 1
    assert version.roles[0].code.code == ROLE_CODES["lab"][0]
    assert version.roles[0].organizationIds == [org.id]
    assert findings == []


def test_attach_organizations_cro_has_no_role_code(real_builder):
    asm = _FakeAsm(real_builder)
    findings = attach_organizations(asm, {"croName": "Acme CRO"})
    version = asm.study.versions[0]
    assert len(version.organizations) == 1 and version.roles == []
    assert version.organizations[0].type.code == ORG_TYPE_CODES["cro"][0]
    assert len(findings) == 1 and "no CDISC study-role code" in findings[0].message


def test_attach_organizations_skips_missing_values(real_builder):
    asm = _FakeAsm(real_builder)
    findings = attach_organizations(asm, {"croName": None, "centralLaboratoryName": ""})
    assert asm.study.versions[0].organizations == [] and findings == []


def test_attach_organizations_handles_no_study(real_builder):
    class NoStudy:
        study = _FakeStudy([])
        _builder = real_builder
    assert attach_organizations(NoStudy(), {"croName": "Acme"}) == []


# --- full pipeline (real assembler) ------------------------------------------------------- #
def test_full_study_attaches_extracted_organizations(doc):
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
                           arms=[{"name": "A", "type": "Experimental"},
                                 {"name": "Placebo", "type": "Placebo Comparator"}])
    study = build_full_study([], design, grid,
                             sites={"croName": "Acme Clinical Research CRO",
                                   "centralLaboratoryName": "Precision Diagnostics Central Lab"})
    assert study["ok"], study["assembler_errors"][:3]
    orgs = {o["name"]: o["type"]["decode"]
           for o in study["wrapper"]["study"]["versions"][0]["organizations"]}
    assert orgs["Acme Clinical Research CRO"] == "Contract Research Organization"
    assert orgs["Precision Diagnostics Central Lab"] == "Laboratory"


def test_sites_field_blocks_when_nothing_extracted():
    """A field with no value BLOCKs through the normal assure() path -- sites
    is not special-cased to auto-accept an absence."""
    from pathlib import Path

    from usdm4_assure.assure import assure
    from usdm4_assure.contracts import Document
    from usdm4_assure.extract.sites import FIELDS as F

    empty = Document(source=Path("x.pdf"), blocks=[], full_text="")
    assured = assure([], empty, F, domain="sites")
    assert all(a.decision is Decision.BLOCK and a.value is None for a in assured)
