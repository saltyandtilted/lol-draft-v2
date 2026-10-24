"""End-to-end recommendation and the v1 comparison function. TEST DATA ONLY."""

import pytest

from model.data import Draft, Mastery, Pick, PlayerProfile
from model.recommend import recommend
from model.v1_baseline import v1_rank
from tests.model_factory import AD_CARRY, AD_TANK, AP_MAGE, AP_TANK, WEAK, make_aggregates

ALL_AD_TEAM = [Pick(50, "JUNGLE"), Pick(51, "MIDDLE"), Pick(52, "BOTTOM"), Pick(53, "UTILITY")]


def ids(rec):
    return [c["champion_id"] for c in rec.candidates]


def test_recommendation_has_full_explanation():
    agg = make_aggregates(matchups=[(AP_TANK, "TOP", 54, 1, 0.15, 40)])
    draft = Draft("TOP", allies=ALL_AD_TEAM, enemies=[Pick(54, "TOP")], bans=[AD_CARRY])

    rec = recommend(agg, draft, smaa_samples=200)

    assert 0 < len(rec.candidates) <= 5
    assert AD_CARRY not in ids(rec)
    best = rec.candidates[0]
    assert best["champion_id"] == AP_TANK  # good matchup and fixes the all-AD team
    assert set(best) >= {"score", "win_estimate", "criteria", "contributions", "why", "games",
                         "interval_pp", "low_data", "top5_probability", "promethee_rank", "vikor_rank"}
    assert best["why"]
    assert 0 <= best["top5_probability"] <= 1
    assert rec.meta["patch"] == "TEST"
    assert rec.meta["known_enemies"] == 1
    assert rec.meta["ahp_cr"] < 0.1
    assert set(rec.meta["spearman"]) == {"promethee_ii", "vikor"}


def test_blind_pick_uses_blind_safety_and_drops_constant_comfort():
    rec = recommend(make_aggregates(), Draft("TOP"), smaa_samples=200)

    # No profile: comfort is 0 for everybody; no allies: nothing to balance.
    assert rec.meta["dropped_criteria"] == ["E", "F"]
    assert rec.meta["win_coefficients"]["S"] > 0
    assert all(c["criteria"]["B"] == 0 for c in rec.candidates)


def test_ban_does_not_reorder_remaining_candidates():
    draft = Draft("TOP", allies=ALL_AD_TEAM)
    before = ids(recommend(make_aggregates(), draft, smaa_samples=100))

    banned = Draft("TOP", allies=ALL_AD_TEAM, bans=[before[0]])
    after = ids(recommend(make_aggregates(), banned, smaa_samples=100))

    assert after[: len(before) - 1] == before[1:]


def test_mastery_is_only_a_comfort_signal():
    # v1 let mastery (weight 0.391) dominate; here a huge mastery on a weak champion is not enough.
    profile = PlayerProfile(mastery={WEAK: Mastery(2_000_000, 0), AD_TANK: Mastery(1_000, 200)})

    rec = recommend(make_aggregates(), Draft("TOP", allies=ALL_AD_TEAM), profile, smaa_samples=100)

    assert rec.candidates[0]["champion_id"] != WEAK


def test_empty_pool_returns_no_candidates():
    draft = Draft("TOP", bans=[AD_TANK, AD_CARRY, AP_MAGE, AP_TANK, WEAK, 54])

    assert recommend(make_aggregates(), draft).candidates == []


V1_TEST_CHAMPIONS = [
    {"Name": "TestTank", "ChampionId": 1, "Position": "Top", "Popularity": 5, "Winrate": 51,
     "DamageType": "AD", "StrongAgainst": [], "WeakAgainst": ["TestEnemy"], "GoodWith": []},
    {"Name": "TestMage", "ChampionId": 3, "Position": "Top", "Popularity": 3, "Winrate": 49,
     "DamageType": "AP", "StrongAgainst": [], "WeakAgainst": [], "GoodWith": []},
    {"Name": "TestEnemy", "ChampionId": 54, "Position": "Top", "Popularity": 4, "Winrate": 50,
     "DamageType": "AD", "StrongAgainst": [], "WeakAgainst": [], "GoodWith": []},
    {"Name": "TestJungle", "ChampionId": 50, "Position": "Jungler", "Popularity": 4, "Winrate": 50,
     "DamageType": "AD", "StrongAgainst": [], "WeakAgainst": [], "GoodWith": []},
]


def test_v1_reproduces_its_reversed_counter():
    # v1 treated "weak against the enemy" as a benefit, so TestTank ranks first. Kept on purpose.
    order = v1_rank(V1_TEST_CHAMPIONS, "TOP", ally_ids=[50], enemy_ids=[54], ban_ids=[])

    assert order[0] == 1
    assert 54 not in order


def test_v1_mastery_dominates():
    order = v1_rank(V1_TEST_CHAMPIONS, "TOP", [], [], [], mastery={3: 500_000})

    assert order[0] == 3


@pytest.mark.parametrize("position", ["JUNGLE", "TOP"])
def test_v1_respects_its_single_role(position):
    order = v1_rank(V1_TEST_CHAMPIONS, position, [], [], [])

    assert (50 in order) == (position == "JUNGLE")


def test_tiny_effects_give_close_call_reason():
    from model.recommend import CLOSE_CALL

    agg = make_aggregates()
    agg.champions["dev_logodds"] = agg.champions["dev_logodds"] / 100  # all nearly equal
    agg.champions["matchup_spread"] = 0.05
    rec = recommend(agg, Draft("TOP"), smaa_samples=50)

    assert rec.candidates[0]["why"] == [CLOSE_CALL]


def test_compare_one_reports_both_versions():
    from model.compare import compare_one

    agg = make_aggregates()
    item = {"label": "TEST", "draft": Draft("TOP", enemies=[Pick(54, "TOP")]), "actual": AD_TANK}

    result = compare_one(agg, V1_TEST_CHAMPIONS, item)

    assert result["v1"] == [1, 3]  # v1 knows only its two test TOP champions besides the enemy
    assert len(result["v2"]) == 5
    assert result["actual_rank_v1"] == 1
    assert result["actual_rank_v2"] >= 1
