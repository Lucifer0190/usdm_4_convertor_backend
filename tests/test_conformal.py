"""Certified auto-accept threshold (task 4.3).

The core check uses synthetic data whose true risk is known in closed form:
scores ~ Beta(a, 1) and P(correct | s) = s, so the true rate of wrong fields
among those with s ≥ t is 1 − E[s | s ≥ t] = 1 − a/(a+1) · (1 − t^(a+1)) / (1 − t^a).
That lets the guarantee — "risk ≤ α with probability ≥ 1 − δ over the
calibration draw" — be checked against the truth rather than another sample.
a = 1 (uniform) is a hard case; a = 5 (most fields likely right, as in a
working pipeline) is where small calibration sets have power.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from usdm4_assure.assure.conformal import (
    DEFAULT_GRID,
    MIN_CALIBRATION,
    ConformalBound,
    aurc,
    binom_cdf,
    calibrate,
    calibration_hash,
    clopper_pearson_upper,
    gate,
    plan_sequence,
    risk_coverage,
)
from usdm4_assure.audit.store import AuditStore
from usdm4_assure.audit.writer import write_calibration, write_field_decision
from usdm4_assure.contracts import AssuredField, Decision
from usdm4_assure.contracts_audit import AuditEvent


def _draw(rng: np.random.Generator, n: int, a: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    s = rng.beta(a, 1.0, n)
    return s, rng.uniform(0, 1, n) < s          # P(correct | s) = s


def _true_risk(t: float, a: float = 1.0) -> float:
    """Exact E[1 - s | s >= t] for s ~ Beta(a, 1)."""
    return 1 - a / (a + 1) * (1 - t ** (a + 1)) / (1 - t ** a)


# --- exact binomial machinery ------------------------------------------------ #
def test_binom_cdf_hand_values():
    assert binom_cdf(1, 2, 0.5) == pytest.approx(0.75)
    assert binom_cdf(0, 10, 0.1) == pytest.approx(0.9 ** 10)
    assert binom_cdf(5, 5, 0.3) == 1.0 and binom_cdf(-1, 5, 0.3) == 0.0


def test_clopper_pearson_zero_errors_matches_closed_form():
    # (1 - p)^45 = 0.1  =>  p = 1 - 0.1^(1/45)
    assert clopper_pearson_upper(0, 45, 0.1) == pytest.approx(1 - 0.1 ** (1 / 45), abs=1e-9)
    assert clopper_pearson_upper(3, 3, 0.1) == 1.0 and clopper_pearson_upper(0, 0, 0.1) == 1.0


# --- the guarantee ------------------------------------------------------------ #
def test_realized_error_among_accepted_is_at_most_alpha():
    rng = np.random.default_rng(0)
    alpha = 0.1
    cal_s, cal_y = _draw(rng, 5000)
    bound = calibrate(cal_s, cal_y, alpha=alpha)
    assert bound.emitted and bound.upper_bound <= alpha
    assert bound.coverage > 0.1                  # certified something non-trivial
    assert _true_risk(bound.threshold) <= alpha + 1e-12      # the guarantee, exactly
    test_s, test_y = _draw(rng, 200_000)
    accepted = test_s >= bound.threshold
    realized = 1 - test_y[accepted].mean()
    noise = 3 * math.sqrt(alpha * (1 - alpha) / accepted.sum())
    assert realized <= alpha + noise                           # and on fresh data


def test_violation_rate_over_calibration_draws_is_at_most_delta():
    alpha, delta, trials, n_cal, a = 0.1, 0.1, 300, 300, 5.0
    rng = np.random.default_rng(1)
    ref_s, ref_y = _draw(rng, 3000, a)           # independent of every calibration draw
    seq = plan_sequence(ref_s, ref_y, n_calibration=n_cal, alpha=alpha)
    emitted = violations = 0
    for _ in range(trials):
        s, y = _draw(rng, n_cal, a)
        b = calibrate(s, y, alpha=alpha, delta=delta, sequence=seq)
        if b.emitted:
            emitted += 1
            violations += _true_risk(b.threshold, a) > alpha
    slack = 3 * math.sqrt(delta * (1 - delta) / trials)
    assert violations / trials <= delta + slack
    assert emitted / trials >= 0.8               # and it has power, not just refusals


def test_planned_sequence_has_more_power_than_default_grid_on_small_sets():
    # Power is a frequency, so it is compared over many calibration draws.
    rng = np.random.default_rng(2)
    ref_s, ref_y = _draw(rng, 3000, 5.0)
    seq = plan_sequence(ref_s, ref_y, n_calibration=300, alpha=0.1)
    planned = default = 0
    for _ in range(100):
        s, y = _draw(rng, 300, 5.0)
        planned += calibrate(s, y, alpha=0.1, sequence=seq).emitted
        default += calibrate(s, y, alpha=0.1).emitted   # 0.99 first: ~15 points, can't pass
    assert planned >= 70 and default <= 10


# --- refusals ------------------------------------------------------------------ #
def test_fewer_than_47_points_refuses_even_if_all_correct():
    b = calibrate([0.999] * (MIN_CALIBRATION - 1), [True] * (MIN_CALIBRATION - 1), alpha=0.1)
    assert not b.emitted and b.threshold is None
    assert str(MIN_CALIBRATION) in b.refused_reason


def test_47_clean_points_is_enough_to_certify():
    b = calibrate([0.999] * MIN_CALIBRATION, [True] * MIN_CALIBRATION, alpha=0.05)
    assert b.emitted and b.n_accepted == MIN_CALIBRATION and b.n_errors_accepted == 0


def test_no_certifiable_threshold_refuses():
    b = calibrate([0.9] * 200, [False] * 200, alpha=0.1)
    assert not b.emitted and "no threshold" in b.refused_reason


@pytest.mark.parametrize("alpha,delta", [(0.0, 0.1), (1.0, 0.1), (0.1, 0.0), (0.1, 1.5)])
def test_invalid_levels_raise(alpha, delta):
    with pytest.raises(ValueError):
        calibrate([0.5] * 50, [True] * 50, alpha=alpha, delta=delta)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        calibrate([0.5] * 50, [True] * 49, alpha=0.1)


# --- exchangeability ------------------------------------------------------------- #
def _emitted_bound() -> ConformalBound:
    return calibrate([0.999] * 60, [True] * 60, alpha=0.1,
                     strata={"study_archetype": ["standard_randomized_phase3"]})


def test_known_family_keeps_the_bound():
    b = _emitted_bound()
    assert b.for_protocol({"study_archetype": "standard_randomized_phase3"}) == b


def test_new_family_trips_exchangeability():
    b = _emitted_bound().for_protocol({"study_archetype": "master_vaccine_protocol"})
    assert not b.emitted and "exchangeability" in b.refused_reason


def test_unrecorded_stratum_trips_rather_than_passing_silently():
    b = _emitted_bound().for_protocol({"sponsor": "Acme"})
    assert not b.emitted and "not recorded" in b.refused_reason


# --- provenance ------------------------------------------------------------------ #
def test_calibration_hash_is_order_independent_and_label_sensitive():
    s, y = [0.9, 0.2, 0.7], [True, False, True]
    h = calibration_hash(s, y)
    assert h == calibration_hash(s[::-1], y[::-1])
    assert h != calibration_hash(s, [True, True, True])


def test_bound_roundtrips_through_dict():
    b = calibrate([0.999] * 60, [True] * 60, alpha=0.1, model_hash="m1",
                  strata={"study_archetype": ["x"]})
    assert ConformalBound.from_dict(b.to_dict()) == b
    assert b.model_hash == "m1" and b.method.startswith("ltt")


def test_bound_and_model_are_logged_in_audit(tmp_path):
    store = AuditStore(tmp_path / "audit.sqlite")
    b = _emitted_bound()
    rec = write_calibration(store, run_id="r1", source_sha256="ab" * 32, bound=b,
                            model={"model_hash": "m1"})
    assert rec.event is AuditEvent.CALIBRATION and rec.threshold == b.threshold
    stored = store.read_all()[0]
    assert stored.verification["conformal"]["calibration_hash"] == b.calibration_hash
    assert stored.verification["confidence_model"] == {"model_hash": "m1"}

    field = AssuredField("studyPhase", "Phase 2", [], True, 2, "supported", 0.99,
                         Decision.AUTO_ACCEPT, domain="metadata")
    frec = write_field_decision(store, run_id="r1", source_sha256="ab" * 32,
                                domain="metadata", assured=field, bound=b)
    assert frec.threshold == b.threshold
    assert frec.verification["conformal"]["calibration_hash"] == b.calibration_hash


# --- risk-coverage --------------------------------------------------------------- #
def test_risk_coverage_hand_case():
    pts = risk_coverage([0.9, 0.8, 0.7, 0.6], [True, False, True, True])
    assert [(p.coverage, p.risk) for p in pts] == [
        (0.25, 0.0), (0.5, 0.5), (0.75, pytest.approx(1 / 3)), (1.0, 0.25)]
    assert aurc([0.9, 0.8, 0.7, 0.6], [True, False, True, True]) == pytest.approx(
        (0 + 0.5 + 1 / 3 + 0.25) / 4)


def test_risk_coverage_ties_are_accepted_together():
    pts = risk_coverage([0.8, 0.8, 0.5], [True, False, True])
    assert [(p.threshold, p.coverage) for p in pts] == [(0.8, pytest.approx(2 / 3)), (0.5, 1.0)]


def test_aurc_empty_is_none():
    assert aurc([], []) is None


# --- gating fields ---------------------------------------------------------------- #
def _fields() -> list[AssuredField]:
    def f(name: str, value: str | None, decision: Decision) -> AssuredField:
        return AssuredField(name, value, [], True, 2, "supported", 0.5, decision,
                            domain="metadata")
    return [f("a", "x", Decision.REVIEW), f("b", "y", Decision.AUTO_ACCEPT),
            f("c", None, Decision.BLOCK)]


def test_gate_accepts_only_above_certified_threshold_and_never_lifts_block():
    fields = _fields()
    res = gate(fields, [0.9995, 0.5, 0.9999], _emitted_bound())
    assert [a.decision for a in fields] == [Decision.AUTO_ACCEPT, Decision.REVIEW,
                                           Decision.BLOCK]
    assert fields[0].confidence == 0.9995 and fields[2].confidence == 0.5  # BLOCK untouched
    assert (res.n_auto_accept, res.n_review, res.n_block) == (1, 1, 1)


def test_gate_with_refused_bound_auto_accepts_nothing():
    fields = _fields()
    res = gate(fields, [0.9999, 0.9999, 0.9999], _emitted_bound(),
               strata={"study_archetype": "master_vaccine_protocol"})
    assert res.n_auto_accept == 0 and not res.bound.emitted
    assert fields[1].decision is Decision.REVIEW      # a previous auto_accept is withdrawn


def test_default_grid_is_strict_to_lenient_and_data_independent():
    assert DEFAULT_GRID == sorted(DEFAULT_GRID, reverse=True)
    assert DEFAULT_GRID[0] == 0.99 and DEFAULT_GRID[-1] == 0.01
