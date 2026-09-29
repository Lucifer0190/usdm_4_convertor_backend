"""Sanity validators and source-independence in the assurance layer.

The regression these guard: in a real run two regex members read the same
running footer ("Phase 1 2 3 4"), agreed on "Phase 1", and outvoted a correct
LLM answer ("3") to reach auto_accept at confidence 1.00. Members that share a
code path are one vote, a value that fails a sanity check can never be
auto-accepted or chosen over a valid one, and deterministic members never
certify themselves without independent confirmation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from usdm4_assure.assure import assure
from usdm4_assure.assure.sanity import check
from usdm4_assure.contracts import Block, Decision, Document, FieldCandidate


def _doc(text: str) -> Document:
    return Document(Path("x.pdf"), [Block(text, 1, (0, 0, 1, 1))], text)


SYNOPSIS = "Protocol Number:\nC5091017\nPhase:\n3\nRationale:\nSomething."


# --- validators -------------------------------------------------------------------- #
def test_phase_must_match_the_synopsis_label_when_present():
    assert check("metadata", "studyPhase", "3", SYNOPSIS).status == "confirmed"
    assert check("metadata", "studyPhase", "Phase 3", SYNOPSIS).status == "confirmed"
    bad = check("metadata", "studyPhase", "Phase 1", SYNOPSIS)
    assert bad.status == "failed" and "synopsis" in bad.reason.lower()


def test_phase_label_on_the_same_line_also_confirms():
    label = "Study Phase: Phase 2\nOther"
    assert check("metadata", "studyPhase", "Phase 2", label).status == "confirmed"
    assert check("metadata", "studyPhase", "Phase 1", label).status == "failed"


def test_phase_without_a_synopsis_label_is_only_shape_checked():
    assert check("metadata", "studyPhase", "Phase 2", "no label here").status == "neutral"
    assert check("metadata", "studyPhase", "banana", "no label here").status == "failed"


@pytest.mark.parametrize("value", [
    "Pfizer Inc. 66 Hudson Boulevard East New York, NY 10001 United States Brief Title:",
    "Pfizer, 500 Main Street, Suite 4",
])
def test_sponsor_with_address_or_label_bleed_fails(value):
    assert check("metadata", "sponsorName", value, "").status == "failed"


def test_clean_sponsor_and_template_codes():
    assert check("metadata", "sponsorName", "Pfizer Inc.", "").status == "neutral"
    assert check("metadata", "protocolIdentifier", "CT02-GSOP", "").status == "failed"
    assert check("metadata", "protocolIdentifier", "C5091017", "").status == "neutral"


@pytest.mark.parametrize("field,value", [
    ("primaryObjective", "."),
    ("primaryEndpoint", "Contents ................................ 41"),
    ("inclusionCriteria", "Description of Change Brief Rationale Section # and Name"),
])
def test_junk_text_fails(field, value):
    domain = "objectives" if field.startswith("primary") else "eligibility"
    assert check(domain, field, value, "").status == "failed"


def test_a_real_objective_passes():
    v = "To compare the efficacy of ibuzatrelvir to placebo in non-hospitalized participants."
    assert check("objectives", "primaryObjective", v, "").status == "neutral"


# --- assurance: independence and sanity ---------------------------------------------- #
def _phase_cands():
    return [FieldCandidate("studyPhase", "Phase 1", "labels", "Phase 1 2 3 4", 1),
            FieldCandidate("studyPhase", "Phase 1", "titlepage", "Phase 1 2 3 4", 1),
            FieldCandidate("studyPhase", "3", "claude", "Phase: 3", 1)]


def test_two_regex_members_do_not_outvote_a_valid_llm_answer():
    out = assure(_phase_cands(), _doc(SYNOPSIS), ["studyPhase"], domain="metadata")[0]
    assert out.value == "3"


def test_without_a_synopsis_label_the_llm_wins_a_tie_but_is_not_auto_accepted_alone():
    out = assure(_phase_cands(), _doc("nothing to confirm"), ["studyPhase"], domain="metadata")[0]
    assert out.value == "3"                 # tie between one deterministic group and one LLM
    assert out.decision is Decision.REVIEW


def test_a_value_that_fails_sanity_is_never_delivered():
    cands = [FieldCandidate("studyPhase", "Phase 1", "labels", "x", 1),
             FieldCandidate("studyPhase", "Phase 1", "titlepage", "x", 1)]
    out = assure(cands, _doc(SYNOPSIS), ["studyPhase"], domain="metadata")[0]
    assert out.value is None and out.decision is Decision.BLOCK


def test_deterministic_only_agreement_needs_independent_confirmation_to_auto_accept():
    cands = [FieldCandidate("studyPhase", "Phase 3", "labels", "Phase: 3", 1),
             FieldCandidate("studyPhase", "Phase 3", "titlepage", "Phase: 3", 1)]
    unconfirmed = assure(cands, _doc("Phase 3 study of ABC."), ["studyPhase"], domain="metadata")[0]
    assert unconfirmed.decision is Decision.REVIEW
    confirmed = assure(cands, _doc(SYNOPSIS), ["studyPhase"], domain="metadata")[0]
    assert confirmed.decision is Decision.AUTO_ACCEPT


def test_two_independent_llm_families_agreeing_can_auto_accept():
    from usdm4_assure.contracts import GroundedCandidate, Method, Quote, VerifyPass
    text = "Sponsor: Northwind Therapeutics."
    q = Quote(text="Northwind Therapeutics", verify_pass=VerifyPass.EXACT, page=1,
              char_start=9, char_end=31, bbox=(0, 0, 1, 1))
    a = GroundedCandidate("sponsorName", "Northwind Therapeutics", Method.LLM_FRONTIER, q,
                          model_id="anthropic/claude-sonnet-5.5")
    b = GroundedCandidate("sponsorName", "Northwind Therapeutics", Method.LLM_FRONTIER, q,
                          model_id="openai/gpt-6-sol")
    out = assure([a, b], _doc(text), ["sponsorName"], domain="metadata")[0]
    assert out.methods_agree and out.decision is Decision.AUTO_ACCEPT
