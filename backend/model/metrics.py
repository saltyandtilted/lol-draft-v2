"""Evaluation metrics for the backtest: win prediction (probabilities) and ranking (hit@k)."""

import numpy as np
import pandas as pd

EPS = 1e-12


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    y, p = np.asarray(y, dtype=float), np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def auc(y: np.ndarray, score: np.ndarray) -> float:
    """Area under the ROC curve via the Mann-Whitney U statistic (ties count half)."""
    y, score = np.asarray(y, dtype=bool), np.asarray(score, dtype=float)
    positives, negatives = y.sum(), (~y).sum()
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = pd.Series(score).rank().to_numpy()  # average ranks handle ties
    u = ranks[y].sum() - positives * (positives + 1) / 2
    return float(u / (positives * negatives))


def accuracy(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) > 0.5) == np.asarray(y, dtype=bool)))


def reliability_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> pd.DataFrame:
    """Mean predicted vs observed rate in equal-count bins (equal width would leave most bins
    empty: draft predictions sit close to 50 %)."""
    df = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": np.asarray(p, dtype=float)})
    df["bin"] = pd.qcut(df["p"].rank(method="first"), q=min(bins, len(df)), labels=False)
    return (df.groupby("bin").agg(predicted=("p", "mean"), observed=("y", "mean"), n=("y", "size"))
            .reset_index(drop=True))


def rank_of(ranking: list[int], item: int) -> int | None:
    """1-based rank of `item` in `ranking`, or None if it is not there."""
    try:
        return ranking.index(item) + 1
    except ValueError:
        return None


def hit_at_k(ranks: list[int | None], k: int) -> float:
    """Share of cases with the actual pick in the top k (missing picks count as misses)."""
    return float(np.mean([r is not None and r <= k for r in ranks])) if ranks else float("nan")


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    return float(np.mean([1 / r if r else 0.0 for r in ranks])) if ranks else float("nan")
