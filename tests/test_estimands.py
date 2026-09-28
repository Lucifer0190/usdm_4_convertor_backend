"""Estimands (task 6.1): grounded extraction, reconciliation, linking, assembly.

Uses a synthetic protocol page with an estimands section written the way
ICH M11 protocols present it (labelled attributes, one paragraph each), plus
stub LLM members returning canned JSON — including one that invents a quote.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf
import pytest

from usdm4_assure.assemble.estimands import link_estimands
from usdm4_assure.contracts import Decision, FindingKind, Method, VerifyPass
from usdm4_assure.extract.estimands import (
    DOMAIN,
    canonical_strategy,
    extract_deterministic,
    extract_estimands,
    extract_llm,
    reconcile,
)
from usdm4_assure.ingest.pdf import ingest

LINES = [
    "3 OBJECTIVES, ENDPOINTS AND ESTIMANDS",
    "Population: Adults with moderate to severe plaque psoriasis.",
    "Endpoint: Proportion achieving PASI 75 at Week 12.",
    "Primary Estimand",
    "Population: Adults with moderate to severe plaque psoriasis who are randomized.",
    "Variable: Achievement of PASI 75 at Week 12.",
    "Treatment: ABC-123 High Dose versus Placebo.",
    ("Intercurrent events: Treatment discontinuation: treatment policy strategy; "
     "Use of rescue medication: composite strategy"),
    "Population-level summary: Difference in proportions between treatment groups.",
    "Secondary Estimand",
    "Population: Adults with moderate to severe plaque psoriasis who are randomized.",
    "Variable: Change from baseline in DLQI at Week 12.",
    "Treatment: ABC-123 Low Dose versus Placebo.",
    "Intercurrent events: Treatment discontinuation: hypothetical strategy",
    "Summary measure: Difference in mean change from baseline.",
]


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    path = tmp_path_factory.mktemp("est") / "estimands.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page(height=900)
    y = 50
    for line in LINES:      # one text block per paragraph, as ingest sees real protocols
        page.insert_textbox(pymupdf.Rect(40, y, 570, y + 45), line, fontsize=9)
        y += 50
    pdf.save(path)
    pdf.close()
    return ingest(path)


class _StubLLM:
    available = True

    def __init__(self, items: list, name: str, model: str):
        self._items, self.name, self.model = items, name, model

    def complete(self, prompt, *, task="extract_prose", system=None, max_tokens=1024):
        return "reasoning" if "YOUR REASONING" not in prompt else json.dumps(self._items)


def _llm_item(variable_quote: str, summary: str = "Difference in proportions between "
              "treatment groups.") -> dict:
    return {
        "name": "Primary Estimand",
        "population": {"value": "Adults randomized",
                       "quote": "Adults with moderate to severe plaque psoriasis who are "
                                "randomized."},
        "variable": {"value": "PASI 75 at Week 12", "quote": variable_quote},
        "treatment": {"value": "ABC-123 High Dose versus Placebo",
                      "quote": "ABC-123 High Dose versus Placebo."},
        "summary_measure": {"value": summary, "quote": summary},
        "intercurrent_events": [
            {"text": "Treatment discontinuation", "strategy": "treatment policy",
             "quote": "Treatment discontinuation: treatment policy strategy"},
            {"text": "Death", "strategy": "composite",
             "quote": "Death is handled with a composite strategy"},   # not in the text
        ],
    }


# --- deterministic member ---------------------------------------------------------- #
def test_deterministic_finds_both_estimands_and_skips_the_synopsis_lines(doc):
    cands = extract_deterministic(doc)
    assert [c.name for c in cands] == ["Primary Estimand", "Secondary Estimand"]
    primary = cands[0]
    assert primary.attributes["variable"].value == "Achievement of PASI 75 at Week 12."
    assert primary.attributes["summary_measure"].value.startswith("Difference in proportions")
    assert all(gv.quote.ok for gv in primary.attributes.values())


def test_deterministic_parses_intercurrent_events_and_strategies(doc):
    primary, secondary = extract_deterministic(doc)
    assert [(i.text, i.strategy) for i in primary.intercurrent_events] == [
        ("Treatment discontinuation", "treatment policy"),
        ("Use of rescue medication", "composite")]
    assert [(i.text, i.strategy) for i in secondary.intercurrent_events] == [
        ("Treatment discontinuation", "hypothetical")]
    assert all(i.quote.ok for i in primary.intercurrent_events)


@pytest.mark.parametrize("text,strategy", [
    ("handled with a treatment-policy approach", "treatment policy"),
    ("While on treatment strategy", "while on treatment"),
    ("principal stratum of responders", "principal stratum"),
    ("no strategy named here", ""),
])
def test_canonical_strategy(text, strategy):
    assert canonical_strategy(text) == strategy


# --- LLM member ------------------------------------------------------------------------ #
def test_llm_member_grounds_every_attribute(doc):
    llm = _StubLLM([_llm_item("Achievement of PASI 75 at Week 12.")], "hard_reasoning",
                   "anthropic/claude-opus-4.8")
    (cand,) = extract_llm(doc, llm)
    assert cand.method is Method.LLM_FRONTIER and cand.model_id == "anthropic/claude-opus-4.8"
    assert cand.prompt_hash and cand.attributes["variable"].quote.ok
    death = next(i for i in cand.intercurrent_events if i.text == "Death")
    assert death.quote.verify_pass is VerifyPass.FAILED


def test_unavailable_or_broken_llm_is_not_a_member(doc):
    class Down:
        available = False
    assert extract_llm(doc, Down()) is None

    class Garbage(_StubLLM):
        def complete(self, prompt, **kw):
            return "not json"
    assert extract_llm(doc, Garbage([], "x", "y")) is None


# --- reconciliation ---------------------------------------------------------------------- #
def test_members_agreeing_on_a_grounded_estimand(doc):
    llm = _StubLLM([_llm_item("Achievement of PASI 75 at Week 12.")], "hard_reasoning", "m1")
    result = extract_estimands(doc, [llm])
    assert result.n_members == 2 and len(result.estimands) == 2
    primary = result.estimands[0]
    summary = primary.attributes["summary_measure"]
    assert summary.methods_agree and summary.n_methods == 2
    assert summary.decision is not Decision.BLOCK
    assert all(f.domain == DOMAIN for f in primary.attributes.values())


def test_hallucinated_quote_blocks_an_llm_only_attribute(doc):
    fabricated = _llm_item("Achievement of PASI 90 at Week 16.")  # not in the text
    only_llm = reconcile([extract_llm(doc, _StubLLM([fabricated], "h", "m1"))], doc)
    assert only_llm.estimands[0].attributes["variable"].decision is Decision.BLOCK
    assert not only_llm.estimands[0].usable


def test_ice_with_no_resolvable_quote_is_dropped_and_reported(doc):
    llm = _StubLLM([_llm_item("Achievement of PASI 75 at Week 12.")], "h", "m1")
    result = extract_estimands(doc, [llm])
    texts = [i.text for i in result.estimands[0].intercurrent_events]
    assert "Death" not in texts and "Treatment discontinuation" in texts
    assert any(f.kind is FindingKind.GROUNDING and "Death" in f.message
               for f in result.findings)
    discontinuation = next(i for i in result.estimands[0].intercurrent_events
                           if i.text == "Treatment discontinuation")
    assert discontinuation.support == 2 and discontinuation.n_members == 2


def test_two_llm_families_plus_deterministic_align_to_the_same_slots(doc):
    item = _llm_item("Achievement of PASI 75 at Week 12.")
    result = extract_estimands(doc, [_StubLLM([item], "hard_reasoning", "m1"),
                                     _StubLLM([item], "extract_alt", "m2")])
    assert result.n_members == 3 and len(result.estimands) == 2


# --- linking + assembly ------------------------------------------------------------------ #
def _objectives_block() -> dict:
    return {"objectives": [
        {"text": "Evaluate efficacy.", "level": "Primary",
         "endpoints": [{"text": "Proportion achieving PASI 75 at Week 12.", "level": "Primary"}]},
        {"text": "Evaluate quality of life.", "level": "Secondary",
         "endpoints": [{"text": "Change from baseline in DLQI at Week 12.",
                        "level": "Secondary"}]}],
        "estimands": []}


def test_link_names_endpoints_and_links_each_estimand(doc):
    result = extract_estimands(doc)
    block, findings = link_estimands(result, _objectives_block(),
                                     ["ABC-123 Low Dose", "ABC-123 High Dose", "Placebo"])
    names = [e["name"] for o in block["objectives"] for e in o["endpoints"]]
    assert names == ["END-1", "END-2"]
    assert [e["endpoint_name"] for e in block["estimands"]] == ["END-1", "END-2"]
    assert block["estimands"][0]["treatment_names"] == ["ABC-123 High Dose", "Placebo"]
    assert block["estimands"][0]["intercurrent_events"][0] == {
        "text": "Treatment discontinuation", "strategy": "treatment policy"}
    assert findings == []


def test_unlinkable_estimand_is_omitted_not_guessed(doc):
    block, findings = link_estimands(extract_estimands(doc), {"objectives": [
        {"text": "Safety.", "level": "Primary",
         "endpoints": [{"text": "Incidence of adverse events.", "level": "Primary"}]}],
        "estimands": []}, ["Placebo"])
    assert block["estimands"] == []
    assert len(findings) == 2 and all("matches no extracted endpoint" in f.message
                                      for f in findings)


def test_linked_estimands_assemble_into_the_usdm_study(doc):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spikes"))
    from make_full_fixture import build

    from usdm4_assure.assemble.study import build_full_study
    from usdm4_assure.extract.design import DesignExtract
    from usdm4_assure.extract.objectives import ObjectivePair, ObjectivesExtract
    from usdm4_assure.extract.soa.crossval import cross_validate
    from usdm4_assure.extract.soa.methods import extract_pdfplumber, extract_pymupdf

    pdf = build()
    grid = cross_validate([extract_pdfplumber(pdf), extract_pymupdf(pdf)])
    design = DesignExtract(intervention_model="Parallel", arms=[
        {"name": "ABC-123 High Dose", "type": "Experimental"},
        {"name": "ABC-123 Low Dose", "type": "Experimental"},
        {"name": "Placebo", "type": "Placebo Comparator"}])
    objs = ObjectivesExtract(items=[
        ObjectivePair("Evaluate efficacy.", "Proportion achieving PASI 75 at Week 12.", "Primary"),
        ObjectivePair("Evaluate quality of life.", "Change from baseline in DLQI at Week 12.",
                      "Secondary")])
    study = build_full_study([], design, grid, objs=objs, estimands=extract_estimands(doc))
    assert study["ok"], study["assembler_errors"][:3]
    assert study["summary"]["estimands"] == 2
    sd = study["wrapper"]["study"]["versions"][0]["studyDesigns"][0]
    endpoint_ids = {e["id"] for o in sd["objectives"] for e in o["endpoints"]}
    assert all(e["variableOfInterestId"] in endpoint_ids for e in sd["estimands"])
    ices = sd["estimands"][0]["intercurrentEvents"]
    assert [i["strategy"] for i in ices] == ["treatment policy", "composite"]
