"""Typed per-field scorer (task 4.1): each verdict on a hand case."""
from __future__ import annotations

from usdm4_assure.eval.labels import FieldLabel
from usdm4_assure.eval.score import score_field, score_fields, score_value, summarize


def _label(domain: str, field: str, value: str, field_type: str) -> FieldLabel:
    return FieldLabel(study_id="S1", domain=domain, field=field, value=value,
                      field_type=field_type, labeler="test", labeled_at="2026-01-01T00:00:00Z")


# --- exact / normalized / miss, all field types -------------------------------- #
def test_exact_match():
    assert score_value("Phase 2", "Phase 2", "scalar") == ("exact", 1.0)


def test_normalized_match_case_and_punctuation():
    verdict, sim = score_value("phase  2.", "Phase 2", "scalar")
    assert (verdict, sim) == ("normalized", 1.0)


def test_scalar_near_miss_is_a_miss_not_fuzzy():
    # "ALEXION" vs "Alexion Pharmaceuticals" -- close but scalars aren't graded on a curve.
    verdict, sim = score_value("ALEXION", "Alexion Pharmaceuticals", "scalar")
    assert verdict == "miss" and 0.0 < sim < 1.0


def test_scalar_unrelated_is_a_miss():
    assert score_value("Sanofi", "Lilly", "scalar")[0] == "miss"


def test_predicted_absent():
    assert score_value(None, "Phase 2", "scalar") == ("predicted_absent", 0.0)
    assert score_value("", "Phase 2", "scalar") == ("predicted_absent", 0.0)


# --- long_text: token overlap --------------------------------------------------- #
def test_long_text_fuzzy_on_overlapping_prose():
    predicted = "Evaluate the safety and efficacy of drug A in adult participants."
    label = "To evaluate safety and tolerability of drug A in adult participants with the disease."
    verdict, sim = score_value(predicted, label, "long_text")
    assert verdict == "fuzzy" and sim >= 0.5


def test_long_text_miss_on_unrelated_prose():
    verdict, sim = score_value("Completely different unrelated sentence about weather.",
                               "Evaluate the safety and efficacy of drug A.", "long_text")
    assert verdict == "miss" and sim < 0.5


# --- number: tolerance ---------------------------------------------------------- #
def test_number_within_tolerance_is_fuzzy():
    # "18.0" vs "18" aren't string-equal (even normalized: punctuation strips the
    # decimal point into a space), so numeric closeness is what carries this.
    verdict, sim = score_value("18.0", "18", "number")
    assert verdict == "fuzzy" and sim == 1.0
    verdict2, sim2 = score_value("18.5", "18", "number")
    assert verdict2 == "fuzzy" and 0.0 < sim2 < 1.0


def test_number_outside_tolerance_is_a_miss():
    verdict, _sim = score_value("25", "18", "number")
    assert verdict == "miss"


def test_number_non_numeric_predicted_is_a_miss():
    assert score_value("adult", "18", "number")[0] == "miss"


# --- score_field / score_fields --------------------------------------------------- #
def test_score_field_carries_label_identity():
    label = _label("metadata", "studyPhase", "Phase 2", "scalar")
    s = score_field("Phase 2", label)
    assert (s.study_id, s.domain, s.field) == ("S1", "metadata", "studyPhase")
    assert s.verdict == "exact" and s.predicted == "Phase 2" and s.label == "Phase 2"


def test_score_fields_missing_prediction_key_is_predicted_absent():
    labels = [_label("metadata", "studyPhase", "Phase 2", "scalar"),
             _label("metadata", "sponsorName", "Acme", "scalar")]
    scores = score_fields({("metadata", "studyPhase"): "Phase 2"}, labels)
    assert [s.verdict for s in scores] == ["exact", "predicted_absent"]


# --- summarize -------------------------------------------------------------------- #
def test_summarize_counts_and_accuracy():
    labels = [_label("metadata", "studyPhase", "Phase 2", "scalar"),
             _label("metadata", "sponsorName", "Acme", "scalar"),
             _label("design", "studyType", "Interventional", "scalar")]
    scores = score_fields({("metadata", "studyPhase"): "Phase 2",
                          ("metadata", "sponsorName"): "Wrong Co"}, labels)
    summary = summarize(scores)
    assert summary["overall"]["n"] == 3
    assert summary["overall"]["verdicts"] == {"exact": 1, "miss": 1, "predicted_absent": 1}
    assert summary["overall"]["accuracy"] == 1 / 3
    assert summary["overall"]["accuracy_of_found"] == 1 / 2   # excludes predicted_absent
    assert summary["by_domain"]["metadata"]["n"] == 2
    assert summary["by_domain"]["design"]["verdicts"] == {"predicted_absent": 1}


def test_summarize_empty_is_none_accuracy_not_a_crash():
    assert summarize([])["overall"]["accuracy"] is None
