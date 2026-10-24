"""Multi-criteria aggregation: TOPSIS with fixed ideals, PROMETHEE II and VIKOR as checks.

Every criterion is scaled to [0, 1] against fixed bounds instead of the current candidate set.
The ideal and anti-ideal are therefore the same for the whole role pool and patch, so banning
one champion cannot reorder the others (it did in v1, which used the current offer).
"""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

LOGODDS_BOUND = 0.5  # about +-12 percentage points of win chance
BOUNDS = {
    "W": (-LOGODDS_BOUND, LOGODDS_BOUND),
    "A": (-LOGODDS_BOUND, LOGODDS_BOUND),
    "B": (-LOGODDS_BOUND, LOGODDS_BOUND),
    "C": (-LOGODDS_BOUND, LOGODDS_BOUND),
    "D": (-LOGODDS_BOUND, LOGODDS_BOUND),
    "S": (-LOGODDS_BOUND, 0.0),
    "E": (0.0, 1.0),
    "F": (-0.3, 0.3),  # one champion rarely moves team quality further
}
PROMETHEE_P = 0.3  # linear preference threshold on the [0, 1] scale
VIKOR_V = 0.5


def normalize(values: pd.DataFrame, bounds=BOUNDS) -> pd.DataFrame:
    if values.isna().any().any():
        raise ValueError("criteria contain missing values")
    out = pd.DataFrame(index=values.index)
    for column in values.columns:
        low, high = bounds[column]
        out[column] = ((values[column] - low) / (high - low)).clip(0, 1)
    return out


def active_criteria(norm: pd.DataFrame, weights: dict) -> tuple[list[str], list[str]]:
    """Criteria with a positive weight and non-zero variance; the rest are dropped and logged."""
    active, dropped = [], []
    for column in norm.columns:
        if weights.get(column, 0) <= 0:
            dropped.append(column)
        elif len(norm) > 1 and np.isclose(norm[column].var(), 0):
            dropped.append(column)
            log.info("criterion %s has zero variance among candidates, dropped", column)
        else:
            active.append(column)
    return active, dropped


def _weight_vector(weights: dict, active: list[str]) -> np.ndarray:
    w = np.array([weights[c] for c in active], dtype=float)
    return w / w.sum()


def topsis(norm: pd.DataFrame, weights: dict, active: list[str]) -> pd.Series:
    """Closeness to the fixed ideal (all ones) versus the fixed anti-ideal (all zeros)."""
    w = _weight_vector(weights, active)
    x = norm[active].to_numpy()
    d_best = np.sqrt((((1 - x) * w) ** 2).sum(axis=1))
    d_worst = np.sqrt(((x * w) ** 2).sum(axis=1))
    return pd.Series(d_worst / (d_best + d_worst), index=norm.index)


def topsis_batch(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """TOPSIS for many weight vectors at once: x is (m, c), w is (s, c); returns (s, m)."""
    d_best = np.sqrt((((1 - x)[None, :, :] * w[:, None, :]) ** 2).sum(axis=2))
    d_worst = np.sqrt(((x[None, :, :] * w[:, None, :]) ** 2).sum(axis=2))
    return d_worst / (d_best + d_worst)


def promethee_ii(norm: pd.DataFrame, weights: dict, active: list[str]) -> pd.Series:
    """Net outranking flow with a linear preference function."""
    w = _weight_vector(weights, active)
    x = norm[active].to_numpy()
    m = len(x)
    if m < 2:
        return pd.Series(0.0, index=norm.index)
    diff = x[:, None, :] - x[None, :, :]
    preference = np.clip(diff / PROMETHEE_P, 0, 1) @ w  # (m, m): how much a beats b
    net = (preference.sum(axis=1) - preference.sum(axis=0)) / (m - 1)
    return pd.Series(net, index=norm.index)


def vikor(norm: pd.DataFrame, weights: dict, active: list[str], v: float = VIKOR_V) -> pd.Series:
    """VIKOR Q (lower is better), with the same fixed ideal as TOPSIS.

    R, the largest single weighted gap, punishes a candidate with one catastrophic weakness.
    """
    w = _weight_vector(weights, active)
    gap = (1 - norm[active].to_numpy()) * w
    s, r = gap.sum(axis=1), gap.max(axis=1)

    def scaled(a):
        span = a.max() - a.min()
        return (a - a.min()) / span if span > 0 else np.zeros_like(a)

    return pd.Series(v * scaled(s) + (1 - v) * scaled(r), index=norm.index)


def spearman(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3:
        return float("nan")
    return float(a.rank().corr(b.rank()))
