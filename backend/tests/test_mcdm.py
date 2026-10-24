"""TOPSIS, PROMETHEE II, VIKOR and SMAA. TEST DATA ONLY: random synthetic criteria."""

import numpy as np
import pandas as pd
import pytest

from model import mcdm, smaa

WEIGHTS = {"A": 0.25, "B": 0.15, "C": 0.1, "D": 0.1, "S": 0.05, "E": 0.2, "F": 0.15}


def random_criteria(n=30, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "A": rng.normal(0, 0.15, n), "B": rng.normal(0, 0.1, n), "C": rng.normal(0, 0.05, n),
        "D": rng.normal(0, 0.1, n), "S": -rng.uniform(0, 0.2, n), "E": rng.uniform(0, 1, n),
        "F": rng.uniform(-0.3, 0.3, n),
    }, index=range(100, 100 + n))


def rank(values: pd.DataFrame):
    norm = mcdm.normalize(values)
    active, _ = mcdm.active_criteria(norm, WEIGHTS)
    return mcdm.topsis(norm, WEIGHTS, active).sort_values(ascending=False)


def test_banning_a_champion_does_not_reorder_the_others():
    values = random_criteria()
    before = rank(values)
    banned = before.index[0]

    after = rank(values.drop(index=banned))

    assert list(after.index) == [c for c in before.index if c != banned]


def test_dominant_candidate_wins_in_all_methods():
    values = random_criteria()
    values.loc[999] = [0.4, 0.3, 0.2, 0.3, 0.0, 1.0, 0.5]
    norm = mcdm.normalize(values)
    active, _ = mcdm.active_criteria(norm, WEIGHTS)

    assert mcdm.topsis(norm, WEIGHTS, active).idxmax() == 999
    assert mcdm.promethee_ii(norm, WEIGHTS, active).idxmax() == 999
    assert mcdm.vikor(norm, WEIGHTS, active).idxmin() == 999


def test_methods_broadly_agree():
    norm = mcdm.normalize(random_criteria())
    active, _ = mcdm.active_criteria(norm, WEIGHTS)
    t = mcdm.topsis(norm, WEIGHTS, active)

    assert mcdm.spearman(t, mcdm.promethee_ii(norm, WEIGHTS, active)) > 0.8
    assert mcdm.spearman(t, -mcdm.vikor(norm, WEIGHTS, active)) > 0.6


def test_zero_variance_and_zero_weight_criteria_are_dropped(caplog):
    values = random_criteria()
    values["C"] = 0.0
    norm = mcdm.normalize(values)

    with caplog.at_level("INFO"):
        active, dropped = mcdm.active_criteria(norm, {**WEIGHTS, "B": 0.0})

    assert set(dropped) == {"B", "C"}
    assert "C has zero variance" in caplog.text
    assert not np.isnan(mcdm.topsis(norm, WEIGHTS, active)).any()


def test_missing_values_are_rejected():
    values = random_criteria()
    values.iloc[0, 0] = np.nan

    with pytest.raises(ValueError):
        mcdm.normalize(values)


def test_values_outside_bounds_are_clipped():
    norm = mcdm.normalize(pd.DataFrame({"A": [-3.0, 0.0, 3.0]}))

    assert list(norm["A"]) == [0.0, 0.5, 1.0]


def test_smaa_is_deterministic_and_sums_to_k():
    norm = mcdm.normalize(random_criteria())
    active, _ = mcdm.active_criteria(norm, WEIGHTS)

    first = smaa.top_k_probability(norm, WEIGHTS, active, samples=300)
    second = smaa.top_k_probability(norm, WEIGHTS, active, samples=300)

    assert first.equals(second)
    assert first.sum() == pytest.approx(5)
    assert first.between(0, 1).all()


def test_smaa_dominant_candidate_is_always_top():
    values = random_criteria()
    values.loc[999] = [0.5, 0.5, 0.5, 0.5, 0.0, 1.0, 1.0]
    norm = mcdm.normalize(values)
    active, _ = mcdm.active_criteria(norm, WEIGHTS)

    assert smaa.top_k_probability(norm, WEIGHTS, active, samples=300)[999] == 1.0


def test_topsis_batch_matches_single_topsis():
    norm = mcdm.normalize(random_criteria())
    active, _ = mcdm.active_criteria(norm, WEIGHTS)
    w = mcdm._weight_vector(WEIGHTS, active)

    batch = mcdm.topsis_batch(norm[active].to_numpy(), w[None, :])[0]

    assert batch == pytest.approx(mcdm.topsis(norm, WEIGHTS, active).to_numpy())
