"""Uniform assurance: every domain yields AssuredFields; a failed quote BLOCKs."""
from __future__ import annotations

from pathlib import Path

from usdm4_assure.assure import assure
from usdm4_assure.contracts import (
    Decision,
    Document,
    FieldCandidate,
    GroundedCandidate,
    Method,
    Quote,
    VerifyPass,
)


def _doc(text: str = "irrelevant document body") -> Document:
    return Document(source=Path("x.pdf"), blocks=[], full_text=text)


def _ok_quote(text: str) -> Quote:
    return Quote(text, VerifyPass.EXACT, page=1, char_start=0, char_end=len(text),
                bbox=(0, 0, 1, 1))


# --- every domain yields AssuredFields ---------------------------------------- #
def test_every_requested_field_gets_an_assured_row_even_with_no_candidates():
    doc = _doc()
    results = assure([], doc, ["studyTitle", "studyPhase"], domain="metadata")
    assert [r.field for r in results] == ["studyTitle", "studyPhase"]
    assert all(r.decision is Decision.BLOCK and r.value is None for r in results)
    assert all(r.domain == "metadata" for r in results)


def test_each_domain_tag_is_carried_onto_its_assured_fields():
    doc = _doc()
    value = "To compare the efficacy of drug A versus placebo"   # long enough to pass sanity
    for domain, field in [("metadata", "studyTitle"), ("design", "studyType"),
                          ("eligibility", "plannedSex"), ("objectives", "primaryObjective")]:
        cands = [FieldCandidate(field, value, "det", value)]
        results = assure(cands, doc, [field], domain=domain)
        assert results[0].domain == domain
        assert results[0].value == value


# --- failed quote => BLOCK ----------------------------------------------------- #
def test_grounded_candidate_with_failed_quote_is_blocked():
    doc = _doc()
    cand = GroundedCandidate("studyTitle", "A Study", Method.LLM_FRONTIER,
                             Quote.failed("not in doc"), model_id="anthropic/claude-sonnet-4.5")
    results = assure([cand], doc, ["studyTitle"], domain="metadata")
    assert results[0].decision is Decision.BLOCK
    assert results[0].confidence == 0.0


def test_partial_grounding_one_ok_one_failed_is_not_blocked():
    """One grounded member's quote fails but another (or a deterministic
    member) supports the same value — the field should not be BLOCKed."""
    doc = _doc("A Study of ABC-123 is a randomized trial.")
    good = GroundedCandidate("studyTitle", "A Study of ABC-123", Method.LLM_FRONTIER,
                             _ok_quote("A Study of ABC-123"), model_id="openai/gpt-5.1")
    bad = GroundedCandidate("studyTitle", "A Study of ABC-123", Method.LLM_SMALL,
                            Quote.failed("A Study of ABC-123"))
    results = assure([good, bad], doc, ["studyTitle"], domain="metadata")
    assert results[0].decision is not Decision.BLOCK
    assert results[0].quote is not None and results[0].quote.ok


def test_ungrounded_deterministic_only_candidate_is_not_forced_to_block():
    """A value with zero GroundedCandidate members has no grounding claim to
    verify, so the legacy deterministic path applies. Policy change (source
    independence): two regex members agreeing is one vote, so on its own it is
    only REVIEW; it reaches auto_accept when the document independently confirms
    the value (here, the synopsis ``Phase:`` label)."""
    cands = [
        FieldCandidate("studyPhase", "Phase 2", "labels", "Phase 2", 1),
        FieldCandidate("studyPhase", "Phase 2", "titlepage", "Phase 2", 1),
    ]
    alone = assure(cands, _doc("Phase 2 study of drug ABC-123."), ["studyPhase"],
                   domain="metadata")[0]
    assert alone.decision is Decision.REVIEW and alone.quote is None
    confirmed = assure(cands, _doc("Phase:\n2\nPhase 2 study of drug ABC-123."),
                       ["studyPhase"], domain="metadata")[0]
    assert confirmed.decision is Decision.AUTO_ACCEPT and confirmed.quote is None


def test_no_value_at_all_is_blocked():
    doc = _doc()
    results = assure([FieldCandidate("studyTitle", None, "labels")], doc,
                     ["studyTitle"], domain="metadata")
    assert results[0].decision is Decision.BLOCK
    assert results[0].value is None


# --- verifier escalation on the uncertain subset only -------------------------- #
class _StubVerifyLLM:
    def __init__(self, verdict: str):
        self.available = True
        self.name = "verify-stub"
        self.verdict = verdict
        self.calls = 0

    def complete(self, prompt, *, task="extract_prose", system=None, max_tokens=1024):
        self.calls += 1
        return self.verdict


def test_verify_llm_escalation_only_fires_on_partial():
    # A "supported" deterministic case (exact token match) must not call the LLM.
    doc = _doc("Sponsor: Northwind Therapeutics.")
    quote = _ok_quote("Northwind Therapeutics")
    cand = GroundedCandidate("sponsorName", "Northwind Therapeutics", Method.LLM_FRONTIER, quote)
    verifier = _StubVerifyLLM("unsupported")  # would flip the result if (wrongly) called
    results = assure([cand], doc, ["sponsorName"], domain="metadata", verify_member=verifier)
    assert results[0].verifier == "supported"
    assert verifier.calls == 0


def test_verify_llm_escalation_resolves_a_partial_verdict():
    doc = _doc("The sponsor entity for this trial is a therapeutics company.")
    # Only 1 of 2 value tokens ("therapeutics") appears in the doc -> "partial".
    quote = _ok_quote("a therapeutics company")
    cand = GroundedCandidate("sponsorName", "Northwind Therapeutics", Method.LLM_FRONTIER, quote)
    verifier = _StubVerifyLLM("supported")
    results = assure([cand], doc, ["sponsorName"], domain="metadata", verify_member=verifier)
    assert verifier.calls == 1
    assert results[0].verifier == "supported"


def test_verify_llm_unavailable_leaves_partial_verdict_as_is():
    doc = _doc("The sponsor entity for this trial is a therapeutics company.")
    quote = _ok_quote("a therapeutics company")
    cand = GroundedCandidate("sponsorName", "Northwind Therapeutics", Method.LLM_FRONTIER, quote)
    results = assure([cand], doc, ["sponsorName"], domain="metadata", verify_member=None)
    assert results[0].verifier == "partial"


# --- agreement across mixed candidate types ------------------------------------ #
def test_agreement_counts_distinct_methods_across_field_and_grounded_candidates():
    doc = _doc("A Study of ABC-123.")
    det = FieldCandidate("studyTitle", "A Study of ABC-123", "titlepage", "A Study of ABC-123", 1)
    llm = GroundedCandidate("studyTitle", "A Study of ABC-123", Method.LLM_FRONTIER,
                            _ok_quote("A Study of ABC-123"))
    results = assure([det, llm], doc, ["studyTitle"], domain="metadata")
    assert results[0].methods_agree
    assert results[0].n_methods == 2
    assert results[0].decision is Decision.AUTO_ACCEPT
