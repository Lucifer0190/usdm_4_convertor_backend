"""The multi-study accuracy rubric (what "89% accurate" means here).

One *item* is one element of a hand-corrected reference USDM: a scalar field, an
identifier, an arm, a criterion, an objective, an endpoint, an estimand, an
epoch, a visit, an activity, a scheduled (visit, activity) mark, an organisation.
An item is *matched* when the delivered study holds an equivalent element.
Accuracy = matched / (reference items + spurious delivered items), so garbage
delivered next to correct answers costs as much as an omission.
"""
from __future__ import annotations

from usdm4_assure.eval.rubric import score_study, view_of


def _study(**over):
    design = {
        "arms": [{"name": "Treatment arm"}, {"name": "Placebo arm"}],
        "epochs": [{"name": "Screening"}, {"name": "Treatment"}],
        "encounters": [{"id": "e1", "name": "Day 1"}, {"id": "e2", "name": "Day 5"}],
        "activities": [{"id": "a1", "name": "Vital signs"}, {"id": "a2", "name": "PK sample"}],
        "eligibilityCriteria": [
            {"text": "Aged 18 years or older at screening.", "category": {"decode": "Inclusion Criteria"}},
            {"text": "Known hypersensitivity to the study drug.", "category": {"decode": "Exclusion Criteria"}}],
        "objectives": [{"text": "Compare efficacy of drug A with placebo.",
                        "level": {"decode": "Trial Primary Objective"},
                        "endpoints": [{"text": "Proportion hospitalised through Day 28."}]}],
        "estimands": [{"name": "Primary", "variableOfInterest": "Proportion hospitalised through Day 28"}],
        "studyPhase": {"decode": "Phase III Trial"},
        "scheduleTimelines": [{"instances": [
            {"encounterId": "e1", "activityIds": ["a1"]},
            {"encounterId": "e2", "activityIds": ["a1", "a2"]}]}],
    }
    design.update(over.pop("design", {}))
    return {"study": {"name": "A phase 3 study", "versions": [{
        "versionIdentifier": "2.0", "studyDesigns": [design],
        "studyIdentifiers": [{"text": "C5091017"}, {"text": "NCT06679140"}],
        "titles": [{"type": {"decode": "Official Study Title"}, "text": "A phase 3 study of drug A"}],
        "organizations": [], **over}]}}


def test_a_perfect_delivery_scores_one_hundred_percent():
    s = score_study(_study(), _study())
    assert s.accuracy == 1.0 and s.spurious == 0


def test_marks_are_scored_as_visit_activity_pairs():
    ref = view_of(_study())
    assert len(ref["marks"]) == 3            # (Day 1, Vital signs), (Day 5, Vital signs), (Day 5, PK)
    got = _study(design={"scheduleTimelines": [{"instances": [
        {"encounterId": "e1", "activityIds": ["a1"]}]}]})
    s = score_study(got, _study())
    assert s.categories["marks"].matched == 1 and s.categories["marks"].reference == 3


def test_spurious_items_lower_accuracy_like_omissions_do():
    junk = [{"text": f"Description of Change Table row {i}", "category": {"decode": "Exclusion Criteria"}}
            for i in range(10)]
    good = _study()["study"]["versions"][0]["studyDesigns"][0]["eligibilityCriteria"]
    got = _study(design={"eligibilityCriteria": good + junk})
    s = score_study(got, _study())
    assert s.categories["criteria"].matched == 2 and s.categories["criteria"].spurious == 10
    assert s.accuracy < 0.7


def test_equivalent_wording_of_scalars_matches():
    ref = _study()
    got = _study(design={"studyPhase": {"decode": "Phase 3"}}, versionIdentifier="Amendment 2")
    s = score_study(got, ref)
    assert s.categories["scalars"].matched == s.categories["scalars"].reference


def test_paraphrased_reference_text_matches_by_token_overlap():
    got = _study(design={"objectives": [{"text": "To compare the efficacy of drug A versus placebo.",
                                         "level": {"decode": "Primary"},
                                         "endpoints": [{"text": "Proportion of participants hospitalised through Day 28."}]}]})
    s = score_study(got, _study())
    assert s.categories["objectives"].matched == 1 and s.categories["endpoints"].matched == 1


def test_categories_absent_from_the_reference_are_not_scored():
    ref = _study(design={"scheduleTimelines": []})
    s = score_study(_study(), ref)
    assert "marks" not in s.categories


def test_numbers_tell_visits_apart():
    from usdm4_assure.eval.rubric import _jaccard
    assert _jaccard("Day 1", "Day 15") < 0.5
    assert _jaccard("Visit 1", "Visit 10") < 0.5
    assert _jaccard("Day -1", "Day 1") < 0.5
    assert _jaccard("Cycle 1 Day 1", "Cycle 1 Day 1") == 1.0


def test_xhtml_escaped_text_compares_as_the_plain_text():
    from usdm4_assure.eval.rubric import _jaccard
    assert _jaccard("ANC &lt;1500/mm3 &amp; platelets", "ANC <1500/mm3 & platelets") == 1.0
