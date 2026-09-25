"""Certified auto-accept threshold — split conformal with a small-sample correction (task 4.3).

**The guarantee, stated exactly (PLAN.md §2.3, DESIGN.md L6).** Given a held-out
calibration set of ``(score, correct)`` pairs exchangeable with future fields,
:func:`calibrate` returns a threshold ``t`` such that, **with probability at least
1 − δ over the draw of the calibration set, the rate of incorrect fields among
those auto-accepted (score ≥ t) is at most α**. It is *marginal* — pooled over
field types, domains and protocols — and says nothing about any one field type
(a 2% global rate can hide a category that is wrong every time). It is void when
exchangeability fails: a new sponsor template, therapeutic area or protocol
family, or a changed parsing stage. Nothing stronger is claimed anywhere.

**How.** Learn-then-Test (Angelopoulos et al., 2021) over a sequence of candidate
thresholds, each hypothesis ``H_t: risk(t) > α`` tested with the *exact* binomial
p-value ``P[Bin(m, α) ≤ k]`` (``m`` accepted, ``k`` of them wrong). That p-value
is the Clopper–Pearson / Beta-quantile form, which is what makes the bound hold
at small ``n`` without asymptotics — the small-sample correction PLAN.md calls
SSBC. Hypotheses are tested in a fixed order and testing stops at the first
non-rejection (fixed-sequence FWER control at δ, no Bonferroni penalty); of the
rejected thresholds the one with the largest calibration coverage is chosen.

The order **must not depend on the calibration set** or the guarantee is lost.
:data:`DEFAULT_GRID` (strict to lenient) is always safe but has little power on
small sets, since its first thresholds accept almost nothing. :func:`plan_sequence`
orders a grid by how likely each threshold is to pass, estimated on an
*independent* reference set (e.g. the confidence model's out-of-fold scores on
its own training data), which is valid and far more powerful.

**Refusals, never guesses.** No threshold is emitted — and so nothing is
auto-accepted on the strength of this module — when the calibration set has
fewer than :data:`MIN_CALIBRATION` points, when no threshold passes, or (at
application time, :meth:`ConformalBound.for_protocol`) when the protocol falls
outside the strata the calibration set covered.

47 is the plan's floor: with zero errors, certifying α = 0.05 at δ = 0.1 needs
at least ``log δ / log(1 − α) ≈ 45`` accepted points, so below ~47 a bound is
essentially unattainable and a "passing" one would be an artefact.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from usdm4_assure.contracts import AssuredField, Decision

MIN_CALIBRATION = 47
DEFAULT_DELTA = 0.1
DEFAULT_GRID: list[float] = [round(1 - i / 100, 2) for i in range(1, 100)]   # 0.99 .. 0.01
METHOD = "ltt_fixed_sequence_exact_binomial"


# --- exact binomial / Beta small-sample machinery ------------------------------ #
def binom_cdf(k: int, m: int, p: float) -> float:
    """``P[Bin(m, p) ≤ k]``, exact, computed in log space."""
    if k < 0:
        return 0.0
    if k >= m:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    log_p, log_q = math.log(p), math.log1p(-p)
    base = math.lgamma(m + 1)
    logs = [base - math.lgamma(i + 1) - math.lgamma(m - i + 1) + i * log_p + (m - i) * log_q
            for i in range(k + 1)]
    top = max(logs)
    return min(1.0, math.exp(top) * math.fsum(math.exp(v - top) for v in logs))


def clopper_pearson_upper(k: int, m: int, delta: float) -> float:
    """One-sided ``1 − δ`` upper confidence bound on a rate from ``k`` of ``m``.

    The ``p`` solving ``P[Bin(m, p) ≤ k] = δ`` — equivalently the ``1 − δ``
    quantile of ``Beta(k + 1, m − k)``.
    """
    if m <= 0 or k >= m:
        return 1.0
    lo, hi = k / m, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if binom_cdf(k, m, mid) > delta:
            lo = mid
        else:
            hi = mid
    return hi


def _p_value(k: int, m: int, alpha: float) -> float:
    """Exact p-value for ``H: risk ≥ α`` given ``k`` wrong among ``m`` accepted."""
    return 1.0 if m == 0 else binom_cdf(k, m, alpha)


# --- the bound --------------------------------------------------------------------- #
@dataclass(frozen=True)
class ConformalBound:
    """A certified threshold, or a documented refusal to certify one."""
    alpha: float
    delta: float
    threshold: float | None
    n_calibration: int
    calibration_hash: str
    model_hash: str | None = None
    n_accepted: int = 0              # calibration points at or above the threshold
    n_errors_accepted: int = 0
    coverage: float = 0.0            # n_accepted / n_calibration
    upper_bound: float | None = None  # 1 − δ Clopper–Pearson bound on risk at the threshold
    strata: dict[str, list[str]] = field(default_factory=dict)
    refused_reason: str | None = None
    method: str = METHOD

    @property
    def emitted(self) -> bool:
        return self.threshold is not None and self.refused_reason is None

    def for_protocol(self, values: dict[str, str] | None) -> ConformalBound:
        """This bound as it applies to one protocol, or a refusal if it is out of scope.

        Every ``(stratum, value)`` pair describing the protocol must have been
        seen at calibration. A stratum the calibration never recorded cannot be
        checked, so it trips too — an unverifiable exchangeability claim is not
        a passed one.
        """
        if not self.emitted:
            return self
        for key, value in (values or {}).items():
            if key not in self.strata:
                return self._refuse(f"exchangeability: stratum {key!r} was not recorded at "
                                    "calibration, so it cannot be checked")
            if value not in self.strata[key]:
                return self._refuse(f"exchangeability: {key}={value!r} is outside the "
                                    f"calibration set ({sorted(self.strata[key])})")
        return self

    def _refuse(self, reason: str) -> ConformalBound:
        return replace(self, threshold=None, refused_reason=reason)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> ConformalBound:
        return cls(**payload)


def calibration_hash(scores: Sequence[float], correct: Sequence[bool],
                     ids: Sequence[str] | None = None) -> str:
    """Order-independent sha256 of the calibration set (ids, scores, labels)."""
    keys = list(ids) if ids is not None else [""] * len(scores)
    rows = sorted(zip(keys, (round(float(s), 12) for s in scores),
                      (int(bool(c)) for c in correct), strict=True))
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _counts(s: np.ndarray, wrong: np.ndarray, t: float) -> tuple[int, int]:
    acc = s >= t
    return int(acc.sum()), int((acc & wrong).sum())


def _validate(alpha: float, delta: float, n_scores: int, n_correct: int) -> None:
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if not 0.0 < delta < 1.0:
        raise ValueError(f"delta must be in (0, 1), got {delta}")
    if n_scores != n_correct:
        raise ValueError(f"{n_scores} scores but {n_correct} labels")


def calibrate(scores: Sequence[float], correct: Sequence[bool], *, alpha: float,
              delta: float = DEFAULT_DELTA, sequence: Sequence[float] | None = None,
              ids: Sequence[str] | None = None, model_hash: str | None = None,
              strata: dict[str, Sequence[str]] | None = None,
              min_n: int = MIN_CALIBRATION) -> ConformalBound:
    """Certify the most permissive auto-accept threshold whose risk is ≤ α w.p. ≥ 1 − δ.

    Args:
        scores: Confidence scores on the held-out calibration set (higher = more
            likely correct). Must not have been used to fit the model or order
            ``sequence``.
        correct: Whether each calibration field's value was right.
        alpha: Target maximum rate of incorrect fields among auto-accepted ones.
        delta: Allowed probability that the calibration draw makes that false.
        sequence: Candidate thresholds in test order, fixed independently of
            this calibration set. Defaults to :data:`DEFAULT_GRID`.
        ids: Optional field identifiers, folded into the calibration hash.
        model_hash: Hash of the confidence model the scores came from.
        strata: Values the calibration set covers per exchangeability stratum
            (e.g. ``{"study_archetype": [...]}``), checked by
            :meth:`ConformalBound.for_protocol`.
        min_n: Refusal floor (default :data:`MIN_CALIBRATION`).
    """
    _validate(alpha, delta, len(scores), len(correct))
    n = len(scores)
    base = ConformalBound(alpha=alpha, delta=delta, threshold=None, n_calibration=n,
                          calibration_hash=calibration_hash(scores, correct, ids),
                          model_hash=model_hash,
                          strata={k: sorted(set(v)) for k, v in (strata or {}).items()})
    if n < min_n:
        return replace(base, refused_reason=(
            f"calibration set has {n} points; at least {min_n} are required before any "
            "bound is emitted"))

    s = np.asarray(scores, dtype=float)
    wrong = ~np.asarray(correct, dtype=bool)
    best: tuple[float, int, int] | None = None
    for t in (sequence if sequence is not None else DEFAULT_GRID):
        m, k = _counts(s, wrong, t)
        if _p_value(k, m, alpha) > delta:
            break                               # fixed sequence: first non-rejection ends it
        if best is None or m > best[1]:
            best = (float(t), m, k)
    if best is None:
        return replace(base, refused_reason=(
            f"no threshold could be certified at alpha={alpha}, delta={delta} "
            f"with {n} calibration points"))
    t, m, k = best
    return replace(base, threshold=t, n_accepted=m, n_errors_accepted=k, coverage=m / n,
                   upper_bound=clopper_pearson_upper(k, m, delta))


def _max_passing_errors(m: int, alpha: float, delta: float) -> int:
    """Largest ``k`` for which ``k`` wrong among ``m`` accepted still certifies (-1: none)."""
    k = -1
    while k + 1 < m and _p_value(k + 1, m, alpha) <= delta:
        k += 1
    return k


def plan_sequence(reference_scores: Sequence[float], reference_correct: Sequence[bool], *,
                  n_calibration: int, alpha: float, delta: float = DEFAULT_DELTA,
                  grid: Sequence[float] | None = None) -> list[float]:
    """Order ``grid`` by each threshold's estimated probability of passing its test.

    Fixed-sequence testing stops at its first non-rejection, so the threshold
    tested first decides whether anything is certified at all; ranking by the
    chance of passing (not by an expected p-value, which is noisy exactly where
    it matters) puts the safest bets first. That chance is estimated from a
    **reference set independent of the calibration set** (typically the
    model's out-of-fold scores on its own training data): with the calibration
    set expected to accept ``m`` fields at a threshold whose reference error
    rate is ``r``, it is ``P[Bin(m, r) ≤ k*]``, ``k*`` being the most errors
    that still certify. Because nothing here looks at calibration data, the
    order is fixed in advance and :func:`calibrate`'s guarantee stands.
    Thresholds the reference set never reaches are dropped; ``r`` is
    Laplace-smoothed so an error-free reference region is not over-trusted.
    """
    s = np.asarray(reference_scores, dtype=float)
    wrong = ~np.asarray(reference_correct, dtype=bool)
    n_ref = len(s)
    ranked = []
    for t in grid if grid is not None else DEFAULT_GRID:
        m_ref, k_ref = _counts(s, wrong, t)
        if m_ref == 0 or n_ref == 0:
            continue
        m_exp = max(1, round(n_calibration * m_ref / n_ref))
        risk = (k_ref + 0.5) / (m_ref + 1)
        p_pass = binom_cdf(_max_passing_errors(m_exp, alpha, delta), m_exp, risk)
        ranked.append((-p_pass, -m_ref, float(t)))
    return [t for _, _, t in sorted(ranked)]


# --- deployment metrics ----------------------------------------------------------- #
@dataclass(frozen=True)
class RiskCoveragePoint:
    threshold: float
    coverage: float
    risk: float


def risk_coverage(scores: Sequence[float], correct: Sequence[bool]) -> list[RiskCoveragePoint]:
    """Risk (error rate among accepted) vs coverage, one point per distinct score."""
    if len(scores) != len(correct):
        raise ValueError(f"{len(scores)} scores but {len(correct)} labels")
    n = len(scores)
    order = sorted(range(n), key=lambda i: -scores[i])
    out: list[RiskCoveragePoint] = []
    errors = 0
    for rank, i in enumerate(order, start=1):
        errors += 0 if correct[i] else 1
        if rank < n and scores[order[rank]] == scores[i]:
            continue                            # ties accept together
        out.append(RiskCoveragePoint(float(scores[i]), rank / n, errors / rank))
    return out


def aurc(scores: Sequence[float], correct: Sequence[bool]) -> float | None:
    """Area under the risk-coverage curve: mean prefix risk over the ranked fields."""
    n = len(scores)
    if n == 0:
        return None
    order = sorted(range(n), key=lambda i: -scores[i])
    errors, total = 0, 0.0
    for rank, i in enumerate(order, start=1):
        errors += 0 if correct[i] else 1
        total += errors / rank
    return total / n


# --- applying a bound to one protocol's fields -------------------------------------- #
@dataclass(frozen=True)
class GateResult:
    bound: ConformalBound            # the bound as it applied to this protocol
    n_auto_accept: int
    n_review: int
    n_block: int


def gate(fields: list[AssuredField], probabilities: Sequence[float], bound: ConformalBound,
         strata: dict[str, str] | None = None) -> GateResult:
    """Replace each field's confidence with its calibrated probability and triage on the bound.

    ``BLOCK`` is untouched — a missing value or a failed quote is a hard gate
    no score can lift. Otherwise a field is ``auto_accept`` only if the bound
    applies to this protocol and its probability clears the threshold; every
    other field goes to ``review``. With no applicable bound nothing is
    auto-accepted: an auto-accept this module cannot back is not made.
    """
    if len(fields) != len(probabilities):
        raise ValueError(f"{len(fields)} fields but {len(probabilities)} probabilities")
    effective = bound.for_protocol(strata)
    for a, p in zip(fields, probabilities, strict=True):
        if a.decision is Decision.BLOCK:
            continue
        a.confidence = float(p)
        accept = effective.emitted and a.value is not None and p >= effective.threshold
        a.decision = Decision.AUTO_ACCEPT if accept else Decision.REVIEW
    tally = {d: sum(a.decision is d for a in fields) for d in Decision}
    return GateResult(effective, tally[Decision.AUTO_ACCEPT], tally[Decision.REVIEW],
                      tally[Decision.BLOCK])
