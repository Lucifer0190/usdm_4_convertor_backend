"""Calibrated per-field confidence (task 4.3, DESIGN.md L6 / §5).

Replaces the hand-set ``assure._confidence`` formula with a fitted model over
:mod:`usdm4_assure.assure.features`: an L2-regularised logistic regression
(DESIGN.md: "fit a small model"), then **Platt recalibration** — a one-feature
logistic on the model's logit — fitted on *out-of-fold* logits so the
recalibration never sees a prediction the model made on its own training rows.
Folds are leave-one-protocol-out when protocol ids are given (DESIGN.md §5: the
unit of generalisation is the protocol, not the field); plain K-fold otherwise;
in-sample only when there is too little data to hold anything out, and that
fallback is recorded on the model rather than hidden.

Pure numpy: no scikit-learn dependency for a 25-weight model. Deterministic —
same rows in, same weights and same :attr:`ConfidenceModel.model_hash` out —
because the hash is what audit records and :class:`ConformalBound` cite.

Accuracy is *measured* by the eval command, never asserted here (DESIGN.md §5):
this module is tested for correctness, not for how good its numbers are.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from usdm4_assure.assure.features import FeatureRow
from usdm4_assure.eval.score import FieldScore

_VERIFY_PASS = ("exact", "normalized", "failed", "none")
_VERIFIER = ("supported", "partial", "unsupported", "n/a")
_FIELD_TYPE = ("scalar", "long_text", "number", "unknown")
_CORRECT_VERDICTS = frozenset({"exact", "normalized", "fuzzy"})
MIN_OOF_ROWS = 10
KFOLD = 5


def _one_hot(prefix: str, value: str, levels: tuple[str, ...]) -> list[tuple[str, float]]:
    return [(f"{prefix}={lvl}", 1.0 if value == lvl else 0.0) for lvl in levels]


def _maybe(name: str, value: float | bool | None) -> list[tuple[str, float]]:
    """A nullable numeric as (value-or-0, is-missing) — missingness is itself a signal."""
    return [(name, 0.0 if value is None else float(value)),
            (f"{name}_missing", 1.0 if value is None else 0.0)]


def _row_features(r: FeatureRow) -> list[tuple[str, float]]:
    return [
        *_one_hot("verify_pass", r.verify_pass, _VERIFY_PASS),
        *_one_hot("verifier", r.verifier, _VERIFIER),
        *_one_hot("field_type", r.field_type if r.field_type in _FIELD_TYPE else "unknown",
                  _FIELD_TYPE),
        ("methods_agree", float(r.methods_agree)),
        ("n_methods", float(min(r.n_methods, 5))),
        *_maybe("agreement_fuzzy_mean", r.agreement_fuzzy_mean),
        ("is_table_cell", float(r.is_table_cell)),
        *_maybe("grid_agreement", r.grid_agreement),
        ("log_span_length", math.log1p(r.span_length)),
        *_maybe("page_position", r.page_position),
        *_maybe("has_text_layer", r.has_text_layer),
        *_maybe("window_kept_ratio", r.window_kept_ratio),
    ]


def _dummy_row() -> FeatureRow:
    return FeatureRow("", "", "", "unknown", False, "none", "n/a", False, 0, None, False, None,
                      0, None, None, None, None, None, 0.0, "review")


FEATURE_COLUMNS: list[str] = [name for name, _ in _row_features(_dummy_row())]


def encode(rows: Sequence[FeatureRow]) -> np.ndarray:
    """``(n, len(FEATURE_COLUMNS))`` design matrix, columns in :data:`FEATURE_COLUMNS` order.

    Identifiers (study, field, route-plan hash) and the old formula's own
    outputs (``confidence``, ``decision``) are deliberately not features.
    """
    return np.array([[v for _, v in _row_features(r)] for r in rows], dtype=float).reshape(
        len(rows), len(FEATURE_COLUMNS))


# --- fitting ------------------------------------------------------------------------ #
def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35.0, 35.0)))


def _fit_logistic(X: np.ndarray, y: np.ndarray, l2: float, max_iter: int = 100) -> np.ndarray:
    """Newton–Raphson on the L2-penalised log-loss; intercept (column 0) unpenalised.

    ``y`` may be soft targets in [0, 1] (Platt's smoothed labels).
    """
    w = np.zeros(X.shape[1])
    penalty = np.full(X.shape[1], l2)
    penalty[0] = 0.0
    for _ in range(max_iter):
        p = _sigmoid(X @ w)
        grad = X.T @ (p - y) + penalty * w
        hess = (X.T * (p * (1 - p))) @ X + np.diag(penalty) + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    return w


def _with_intercept(X: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((X.shape[0], 1)), X])


def _folds(n: int, groups: Sequence[str] | None) -> tuple[str, list[np.ndarray]]:
    """Held-out index sets: leave-one-protocol-out, K-fold, or none."""
    if groups is not None and len(set(groups)) >= 2:
        g = np.asarray(groups)
        return "lopo", [np.flatnonzero(g == v) for v in sorted(set(groups))]
    if n >= MIN_OOF_ROWS:
        idx = np.arange(n)
        return "kfold", [idx[idx % KFOLD == f] for f in range(KFOLD)]
    return "in_sample", []


def _platt_targets(y: np.ndarray) -> np.ndarray:
    """Platt (1999) smoothed targets — keeps the 1-D fit finite on separable data."""
    n_pos, n_neg = float(y.sum()), float(len(y) - y.sum())
    return np.where(y > 0.5, (n_pos + 1) / (n_pos + 2), 1 / (n_neg + 2))


@dataclass
class ConfidenceModel:
    """Logistic model + Platt recalibration. ``predict_proba`` is the calibrated score."""
    weights: list[float]
    platt_a: float
    platt_b: float
    platt_mode: str                  # lopo | kfold | in_sample
    l2: float
    n_train: int
    training_hash: str
    columns: list[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    fitted_at: str = ""

    @classmethod
    def fit(cls, rows: Sequence[FeatureRow], correct: Sequence[bool],
            groups: Sequence[str] | None = None, l2: float = 1.0) -> ConfidenceModel:
        if len(rows) != len(correct):
            raise ValueError(f"{len(rows)} rows but {len(correct)} labels")
        if not rows:
            raise ValueError("cannot fit a confidence model on zero rows")
        X = _with_intercept(encode(rows))
        y = np.asarray(correct, dtype=float)
        mode, folds = _folds(len(rows), groups)
        oof = np.empty(len(rows))
        if folds:
            for held in folds:
                train = np.setdiff1d(np.arange(len(rows)), held)
                oof[held] = X[held] @ _fit_logistic(X[train], y[train], l2)
        w = _fit_logistic(X, y, l2)
        if not folds:
            oof = X @ w
        # Platt: slope + intercept on the out-of-fold logit. A token penalty keeps the
        # slope finite when every logit is identical (nothing to recalibrate on).
        a, b = _fit_logistic(np.column_stack([np.ones(len(oof)), oof]), _platt_targets(y),
                             l2=1e-6)[::-1]
        return cls(weights=[float(v) for v in w], platt_a=float(a), platt_b=float(b),
                   platt_mode=mode, l2=l2, n_train=len(rows),
                   training_hash=training_hash(rows, correct, groups),
                   fitted_at=datetime.now(UTC).isoformat(timespec="seconds"))

    def logits(self, rows: Sequence[FeatureRow]) -> np.ndarray:
        if self.columns != FEATURE_COLUMNS:
            raise ValueError("model was fitted on a different feature set; refit it")
        return _with_intercept(encode(rows)) @ np.asarray(self.weights)

    def predict_proba(self, rows: Sequence[FeatureRow]) -> np.ndarray:
        """Calibrated probability that each field's value is correct."""
        return _sigmoid(self.platt_a * self.logits(rows) + self.platt_b)

    @property
    def model_hash(self) -> str:
        """sha256 over everything that determines a prediction (not ``fitted_at``)."""
        payload = {"weights": [round(v, 12) for v in self.weights],
                   "platt": [round(self.platt_a, 12), round(self.platt_b, 12)],
                   "columns": self.columns, "l2": self.l2, "training_hash": self.training_hash}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def to_dict(self) -> dict:
        return {"weights": self.weights, "platt_a": self.platt_a, "platt_b": self.platt_b,
                "platt_mode": self.platt_mode, "l2": self.l2, "n_train": self.n_train,
                "training_hash": self.training_hash, "columns": self.columns,
                "fitted_at": self.fitted_at, "model_hash": self.model_hash}

    @classmethod
    def from_dict(cls, payload: dict) -> ConfidenceModel:
        data = {k: v for k, v in payload.items() if k != "model_hash"}
        model = cls(**data)
        if "model_hash" in payload and payload["model_hash"] != model.model_hash:
            raise ValueError("stored model_hash does not match the stored parameters")
        return model

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> ConfidenceModel:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def training_hash(rows: Sequence[FeatureRow], correct: Sequence[bool],
                  groups: Sequence[str] | None = None) -> str:
    """Order-independent sha256 of a training set (features, labels, groups)."""
    g = list(groups) if groups is not None else [""] * len(rows)
    items = sorted(json.dumps([gi, r.to_dict(), bool(c)], sort_keys=True, default=str)
                   for r, c, gi in zip(rows, correct, g, strict=True))
    return hashlib.sha256("\n".join(items).encode()).hexdigest()


# --- labels -> training pairs, and calibration quality ------------------------------ #
def training_pairs(rows: Sequence[FeatureRow], scores: Sequence[FieldScore]
                   ) -> tuple[list[FeatureRow], list[bool], list[str]]:
    """Join features to scored labels on (study, domain, field).

    Only fields that both produced a value and have a label are kept: a field
    with no value is a ``BLOCK`` and can never be auto-accepted, so it has no
    place in a model of "is this accepted value right".
    """
    by_key = {(s.study_id, s.domain, s.field): s for s in scores}
    out_rows, out_y, out_g = [], [], []
    for r in rows:
        s = by_key.get((r.study_id, r.domain, r.field))
        if s is None or s.verdict == "predicted_absent" or not r.value_present:
            continue
        out_rows.append(r)
        out_y.append(s.verdict in _CORRECT_VERDICTS)
        out_g.append(r.study_id)
    return out_rows, out_y, out_g


def brier(probabilities: Sequence[float], correct: Sequence[bool]) -> float | None:
    """Brier score — DESIGN.md §5's headline (strictly proper) calibration metric."""
    if len(probabilities) != len(correct):
        raise ValueError(f"{len(probabilities)} probabilities but {len(correct)} labels")
    if not len(correct):
        return None
    p = np.asarray(probabilities, dtype=float)
    return float(np.mean((p - np.asarray(correct, dtype=float)) ** 2))
