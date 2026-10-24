"""Aggregation tests. TEST DATA ONLY: synthetic participant rows, no real matches."""

import numpy as np
import pandas as pd
import pytest

from pipeline import aggregate as agg
from pipeline.collect import RunStats, collect
from tests.match_factory import TEST_CHAMPION_IDS, make_match
from tests.test_collect import FakeRiotClient, conn  # noqa: F401  (fixture)


def rows(champion_id, position, wins, losses, patch="16.21", w=1.0):
    return [
        {"champion_id": champion_id, "position": position, "win": int(i < wins), "patch": patch, "w": w}
        for i in range(wins + losses)
    ]


def role_pool(extra=()):
    """TOP pool of 20 champions around 50 % plus optional extra rows."""
    data = []
    rng = np.random.default_rng(0)
    for champion_id in range(100, 120):
        wins = int(rng.integers(45, 56))
        data += rows(champion_id, "TOP", wins, 100 - wins)
    data += list(extra)
    return pd.DataFrame(data)


def test_one_game_champion_is_shrunk_to_role_mean():
    stats = agg.champion_role_stats(role_pool(rows(1, "TOP", 1, 0)))
    one_game = stats[stats["champion_id"] == 1].iloc[0]

    assert one_game["games"] == 1
    assert one_game["low_data"]
    assert abs(one_game["dev_logodds"]) < 0.05


def test_larger_sample_keeps_more_signal():
    # Both champions win 60 %; the one with 10x more games is shrunk less.
    stats = agg.champion_role_stats(role_pool(rows(2, "TOP", 300, 200) + rows(4, "TOP", 30, 20)))
    stats = stats.set_index("champion_id")
    big, small = stats.loc[2], stats.loc[4]

    assert not big["low_data"]
    assert 0 < small["dev_logodds"] < big["dev_logodds"] < agg.logit(0.6)
    assert big["ci_high"] - big["ci_low"] < small["ci_high"] - small["ci_low"]
    assert big["ci_low"] < big["posterior_mean"] < big["ci_high"]


def test_role_share_identifies_flex_picks():
    data = role_pool(rows(3, "TOP", 30, 30) + rows(3, "MIDDLE", 30, 30) + rows(3, "UTILITY", 1, 1))
    stats = agg.champion_role_stats(data).set_index(["champion_id", "position"])

    assert stats.loc[(3, "TOP"), "role_share"] == pytest.approx(60 / 122)
    assert stats.loc[(3, "UTILITY"), "role_share"] < 0.05


def test_older_patch_has_half_weight():
    data = pd.DataFrame(rows(1, "TOP", 10, 0, patch="16.21") + rows(1, "TOP", 0, 10, patch="16.20")
                        + rows(1, "TOP", 0, 10, patch="16.19"))
    weighted, patches = agg.add_patch_weights(data.drop(columns="w"))

    assert patches == ["16.21", "16.20"]
    assert len(weighted) == 20
    assert weighted.groupby("patch")["w"].first().to_dict() == {"16.20": 0.5, "16.21": 1.0}


def test_shift_equals_shrunk_deviation_when_expectation_is_even():
    # 100 games at 60 % with expected p = 0.5.
    pairs = pd.DataFrame({"key": 1, "win": [1] * 60 + [0] * 40, "w": 1.0, "expected": 0.0})
    out = agg._shift(pairs, ["key"], 1 / agg.PRIOR_SD["lane"] ** 2).iloc[0]

    raw_one_step = 10 / 25
    k = agg.prior_games("lane")
    assert out["shift"] == pytest.approx(100 / (100 + k) * raw_one_step)
    assert out["low_data"] == False  # noqa: E712  (numpy bool)


def test_shift_with_few_games_stays_small():
    pairs = pd.DataFrame({"key": 1, "win": [1, 1, 1], "w": 1.0, "expected": 0.0})

    assert 0 < agg._shift(pairs, ["key"], 1 / agg.PRIOR_SD["lane"] ** 2).iloc[0]["shift"] < 0.05


def test_shift_accounts_for_expected_strength():
    # A strong champion winning exactly as often as expected has no matchup bonus.
    expected = 0.4
    n = 1000
    wins = round(agg.sigmoid(expected) * n)
    pairs = pd.DataFrame({"key": 1, "win": [1] * wins + [0] * (n - wins), "w": 1.0, "expected": expected})

    assert abs(agg._shift(pairs, ["key"], 1 / agg.PRIOR_SD["lane"] ** 2).iloc[0]["shift"]) < 0.01


def test_aggregate_on_database_writes_tables_without_missing_values(conn):  # noqa: F811
    matches = {f"EUN1_{i}": make_match(f"EUN1_{i}", blue_win=i % 3 != 0) for i in range(40)}
    client = FakeRiotClient(matches, {"TEST-GOLD-I-a": list(matches)})
    collect(
        conn, client, TEST_CHAMPION_IDS, 1, tiers=["GOLD"], players_per_tier=1,
        matches_per_player=100, max_matches=100, start_time=None, stats=RunStats(),
    )

    summary = agg.aggregate(conn)

    assert summary["matches_used"] == 40
    assert summary["current_patch"] == "15.20"
    for table in ("champion_role_stats", "matchup_stats", "duo_stats", "champion_profile"):
        frame = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        assert not frame.empty
        assert not frame.isna().any().any()
    profile = pd.read_sql_query("SELECT * FROM champion_profile WHERE position = 'ALL'", conn)
    top = profile[profile["champion_id"] == 1].iloc[0]  # even slot: physical damage dealer
    assert top["physical_share"] > 0.8
    assert "warnings" in agg.to_markdown(summary).lower()


def test_aggregate_refuses_empty_database(conn):  # noqa: F811
    with pytest.raises(ValueError):
        agg.aggregate(conn)


def test_rare_champion_does_not_look_safer_than_role_average():
    champions = pd.DataFrame({
        "position": ["TOP", "TOP", "TOP"],
        "games": [500, 500, 2],
        "w_games": [500.0, 500.0, 2.0],
        "matchup_spread": [0.05, 0.07, 0.0],
    })

    spread = agg.smooth_spread(champions)

    assert spread[2] == pytest.approx(0.06, abs=0.002)
    assert spread[0] == pytest.approx(0.05, abs=0.003)


def test_duo_prior_is_stronger_than_lane_prior():
    # One win with a new ally must not outweigh a champion's whole strength estimate.
    pairs = pd.DataFrame({"key": 1, "win": [1], "w": 1.0, "expected": 0.0})
    lane = agg._shift(pairs, ["key"], 1 / agg.PRIOR_SD["lane"] ** 2).iloc[0]["shift"]
    duo = agg._shift(pairs, ["key"], 1 / agg.PRIOR_SD["duo"] ** 2).iloc[0]["shift"]

    assert 0 < duo < lane < 0.015
    assert agg.prior_games("off_lane") > agg.prior_games("duo") > agg.prior_games("lane")
