"""Calibrated confidence model (task 4.3): correctness, determinism, provenance.

Accuracy is measured by the eval command, not asserted here (DESIGN.md §5) —
these tests check that the model learns an obvious signal, is deterministic,
recalibrates out-of-fold, and round-trips with a stable hash.
"""
from __future__ import annotations

import numpy as np
import pytest

from usdm4_assure.assure.confidence import (
    FEATURE_COLUMNS,
    ConfidenceModel,
    brier,
    encode,
    training_pairs,
)
from usdm4_assure.assure.features import FeatureRow
from usdm4_assure.eval.score import FieldScore


def _row(study: str = "S1", field: str = "f", verify_pass: str = "exact",
         verifier: str = "supported", agree: bool = True, page_position: float | None = 0.1,
         value_present: bool = True) -> FeatureRow:
    return FeatureRow(study, "metadata", field, "scalar", value_present, verify_pass, verifier,
                      agree, 2 if agree else 1, None, False, None, 20, 1, page_position, True,
                      0.9, "h", 0.5, "review")


def _synthetic(n_per: int = 40, studies: int = 4, seed: int = 0):
    """Grounded+agreeing fields are ~95% right; failed-quote fields ~10% right."""
    rng = np.random.default_rng(seed)
    rows, y, groups = [], [], []
    for sid in range(studies):
        for i in range(n_per):
            good = i % 2 == 0
            rows.append(_row(study=f"S{sid}", field=f"f{i}",
                             verify_pass="exact" if good else "failed",
                             verifier="supported" if good else "unsupported", agree=good))
            y.append(bool(rng.uniform() < (0.95 if good else 0.10)))
            groups.append(f"S{sid}")
    return rows, y, groups


# --- encoding ---------------------------------------------------------------- #
def test_encode_shape_and_column_order():
    X = encode([_row(), _row(verify_pass="failed")])
    assert X.shape == (2, len(FEATURE_COLUMNS))
    i = FEATURE_COLUMNS.index("verify_pass=exact")
    assert X[0, i] == 1.0 and X[1, i] == 0.0


def test_missing_values_get_an_indicator_not_a_guess():
    X = encode([_row(page_position=None), _row(page_position=0.4)])
    v, miss = FEATURE_COLUMNS.index("page_position"), FEATURE_COLUMNS.index(
        "page_position_missing")
    assert (X[0, v], X[0, miss]) == (0.0, 1.0) and (X[1, v], X[1, miss]) == (0.4, 0.0)


def test_identifiers_and_old_formula_outputs_are_not_features():
    assert not {"study_id", "field", "route_plan_hash", "confidence", "decision"} & set(
        FEATURE_COLUMNS)


# --- fitting -------------------------------------------------------------------- #
def test_learns_the_grounding_signal():
    rows, y, groups = _synthetic()
    m = ConfidenceModel.fit(rows, y, groups)
    good, bad = m.predict_proba([_row(), _row(verify_pass="failed", verifier="unsupported",
                                              agree=False)])
    assert 0.0 < bad < good < 1.0 and good > 0.8 and bad < 0.3


def test_recalibration_is_leave_one_protocol_out_with_groups():
    rows, y, groups = _synthetic()
    assert ConfidenceModel.fit(rows, y, groups).platt_mode == "lopo"
    assert ConfidenceModel.fit(rows, y).platt_mode == "kfold"
    assert ConfidenceModel.fit(rows[:6], y[:6]).platt_mode == "in_sample"


def test_fit_is_deterministic():
    rows, y, groups = _synthetic()
    assert ConfidenceModel.fit(rows, y, groups).model_hash == \
        ConfidenceModel.fit(rows, y, groups).model_hash


def test_single_class_labels_do_not_blow_up():
    rows, _, groups = _synthetic()
    p = ConfidenceModel.fit(rows, [True] * len(rows), groups).predict_proba(rows)
    assert np.all(np.isfinite(p)) and np.all(p > 0.5)


def test_fit_rejects_mismatched_or_empty_input():
    with pytest.raises(ValueError):
        ConfidenceModel.fit([_row()], [True, False])
    with pytest.raises(ValueError):
        ConfidenceModel.fit([], [])


# --- provenance -------------------------------------------------------------------- #
def test_save_load_roundtrip_same_predictions_and_hash(tmp_path):
    rows, y, groups = _synthetic()
    m = ConfidenceModel.fit(rows, y, groups)
    loaded = ConfidenceModel.load(m.save(tmp_path / "model.json"))
    assert loaded.model_hash == m.model_hash
    assert np.allclose(loaded.predict_proba(rows), m.predict_proba(rows))


def test_tampered_parameters_fail_the_hash_check():
    rows, y, groups = _synthetic()
    payload = ConfidenceModel.fit(rows, y, groups).to_dict()
    payload["weights"][1] += 1.0
    with pytest.raises(ValueError):
        ConfidenceModel.from_dict(payload)


def test_training_data_changes_the_hash():
    rows, y, groups = _synthetic()
    flipped = [not y[0], *y[1:]]
    assert ConfidenceModel.fit(rows, y, groups).training_hash != \
        ConfidenceModel.fit(rows, flipped, groups).training_hash


# --- labels -> training pairs ------------------------------------------------------ #
def _score(study: str, field: str, verdict: str) -> FieldScore:
    return FieldScore(study, "metadata", field, verdict, 1.0, "v", "v")


def test_training_pairs_joins_and_drops_unscorable_fields():
    rows = [_row("S1", "a"), _row("S1", "b"), _row("S1", "c"),
            _row("S1", "d", value_present=False), _row("S1", "unlabelled")]
    scores = [_score("S1", "a", "exact"), _score("S1", "b", "fuzzy"), _score("S1", "c", "miss"),
              _score("S1", "d", "predicted_absent")]
    kept, y, groups = training_pairs(rows, scores)
    assert [r.field for r in kept] == ["a", "b", "c"]
    assert y == [True, True, False] and groups == ["S1"] * 3


# --- calibration metric ------------------------------------------------------------ #
def test_brier_hand_values():
    assert brier([1.0, 0.0], [True, True]) == 0.5
    assert brier([0.8], [True]) == pytest.approx(0.04)
    assert brier([], []) is None
