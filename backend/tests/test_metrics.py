"""Metric tests on hand-made inputs with known answers."""

import math

import numpy as np
import pytest

from model import metrics


def test_log_loss_of_coin_flip_is_ln2():
    assert metrics.log_loss([1, 0, 1, 0], [0.5] * 4) == pytest.approx(math.log(2))


def test_log_loss_survives_certain_wrong_prediction():
    assert np.isfinite(metrics.log_loss([1], [0.0]))


def test_brier():
    assert metrics.brier([1, 0], [0.5, 0.5]) == pytest.approx(0.25)
    assert metrics.brier([1, 0], [1.0, 0.0]) == 0.0


def test_auc_perfect_reversed_and_ties():
    y = [0, 0, 1, 1]
    assert metrics.auc(y, [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert metrics.auc(y, [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert metrics.auc(y, [0.5, 0.5, 0.5, 0.5]) == 0.5


def test_auc_of_noise_is_about_half():
    rng = np.random.default_rng(0)
    assert metrics.auc(rng.integers(0, 2, 5000), rng.random(5000)) == pytest.approx(0.5, abs=0.03)


def test_reliability_bins_have_equal_counts():
    p = np.linspace(0.4, 0.6, 100)
    bins = metrics.reliability_bins(np.ones(100), p, bins=4)
    assert list(bins["n"]) == [25, 25, 25, 25]
    assert bins["predicted"].is_monotonic_increasing


def test_rank_hit_and_mrr():
    assert metrics.rank_of([5, 7, 9], 7) == 2
    assert metrics.rank_of([5, 7, 9], 1) is None
    ranks = [1, 3, None, 6]
    assert metrics.hit_at_k(ranks, 1) == 0.25
    assert metrics.hit_at_k(ranks, 5) == 0.5
    assert metrics.mean_reciprocal_rank(ranks) == pytest.approx((1 + 1 / 3 + 0 + 1 / 6) / 4)
