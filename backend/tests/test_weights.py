"""AHP, dynamic weights and the diagnostic regression. TEST DATA ONLY."""

import numpy as np
import pytest

from model.ahp import AhpError, priorities
from model.regression import fit_logistic
from model.weights import GOAL_MATRIX, goal_weights, win_coefficients


def test_consistent_matrix_gives_known_weights():
    # Perfectly consistent: weights 4 : 2 : 1.
    matrix = [[1, 2, 4], [1 / 2, 1, 2], [1 / 4, 1 / 2, 1]]

    w, cr = priorities(matrix)

    assert w == pytest.approx([4 / 7, 2 / 7, 1 / 7])
    assert cr == pytest.approx(0, abs=1e-9)


def test_non_reciprocal_matrix_is_rejected():
    # Like v1: a_12 = 1/7 but a_21 = 5.
    matrix = [[1, 1 / 7, 3], [5, 1, 3], [1 / 3, 1 / 3, 1]]

    with pytest.raises(AhpError, match="reciprocal"):
        priorities(matrix)


def test_inconsistent_matrix_is_rejected():
    # A > B > C but C >> A.
    matrix = [[1, 5, 1 / 7], [1 / 5, 1, 5], [7, 1 / 5, 1]]

    with pytest.raises(AhpError, match="inconsistent"):
        priorities(matrix)


def test_default_goal_matrix_is_consistent():
    w, cr = priorities(GOAL_MATRIX)

    assert cr < 0.1
    assert w[0] > max(w[1], w[2])  # winning dominates; comfort and balance about equal


def test_goal_weights_sum_to_one_and_favour_winning():
    w, cr = goal_weights()

    assert sum(w.values()) == pytest.approx(1.0)
    assert w["W"] > 0.7
    assert cr < 0.1


def test_full_comfort_is_worth_only_a_few_percentage_points():
    # Swing weighting: E from 0 to 1 must equal a small shift of W (v1 let mastery dominate).
    from model.mcdm import BOUNDS

    w, _ = goal_weights()
    low, high = BOUNDS["W"]
    logodds_equivalent = w["E"] / w["W"] * (high - low)
    percentage_points = (1 / (1 + np.exp(-logodds_equivalent)) - 0.5) * 100

    assert 2 < percentage_points < 5


def test_win_block_has_equal_weights_and_blind_safety_fades():
    blind, middle, last = win_coefficients(0), win_coefficients(2), win_coefficients(5)

    assert blind["A"] == blind["B"] == blind["C"] == blind["D"] == 1.0
    assert blind["S"] > middle["S"] > last["S"] == 0


def test_invalid_phase_rejected():
    with pytest.raises(ValueError):
        win_coefficients(6)


def test_logistic_regression_recovers_coefficient():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(5000, 1))
    y = (rng.random(5000) < 1 / (1 + np.exp(-(0.2 + 1.5 * x[:, 0])))).astype(float)

    beta = fit_logistic(x, y, l2=0.1)

    assert beta[0] == pytest.approx(0.2, abs=0.1)
    assert beta[1] == pytest.approx(1.5, abs=0.15)
