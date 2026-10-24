"""Criteria A-F on synthetic aggregates. TEST DATA ONLY."""

import pytest

from model import criteria
from model.data import Draft, Mastery, Pick, PlayerGame, PlayerProfile
from tests.model_factory import AD_CARRY, AD_TANK, AP_MAGE, AP_TANK, FLEX, WEAK, make_aggregates

ALL_AD_TEAM = [Pick(50, "JUNGLE"), Pick(51, "MIDDLE"), Pick(52, "BOTTOM"), Pick(53, "UTILITY")]


def test_candidates_respect_role_share_bans_and_picks():
    agg = make_aggregates()
    draft = Draft("TOP", enemies=[Pick(WEAK, "TOP")], bans=[AP_TANK])

    ids = set(criteria.candidates(agg, draft).index)

    assert ids == {AD_TANK, AD_CARRY, AP_MAGE, 54}  # 54 is the test TOP enemy laner
    assert FLEX not in ids  # 3 % of its games in TOP


def test_a_is_smoothed_strength():
    out = criteria.compute(make_aggregates(), Draft("TOP"))

    assert out.loc[AD_TANK, "A"] == pytest.approx(0.10)
    assert out.loc[WEAK, "A"] < 0


def test_b_counts_lane_opponent_fully_and_others_half():
    agg = make_aggregates(matchups=[
        (AD_TANK, "TOP", 54, 1, -0.3, 40),   # bad lane matchup
        (AD_TANK, "TOP", 50, 0, 0.2, 40),    # good against the enemy jungler
        (AP_MAGE, "TOP", 54, 1, 0.1, 40),
    ])
    draft = Draft("TOP", enemies=[Pick(54, "TOP"), Pick(50, "JUNGLE")])

    out = criteria.compute(agg, draft)

    assert out.loc[AD_TANK, "B"] == pytest.approx(-0.3 + 0.5 * 0.2)
    assert out.loc[AP_MAGE, "B"] == pytest.approx(0.1)
    assert out.loc[AD_CARRY, "B"] == 0  # no data: no counter effect
    assert out.loc[AD_TANK, "games_B"] == 80


def test_b_is_bad_for_countered_candidate():
    # v1 had this reversed: being weak against an enemy must lower the score.
    agg = make_aggregates(matchups=[(WEAK, "TOP", 54, 1, -0.4, 50)])

    out = criteria.compute(agg, Draft("TOP", enemies=[Pick(54, "TOP")]))

    assert out.loc[WEAK, "B"] < 0


def test_c_sums_duo_shifts():
    agg = make_aggregates(duos=[(AP_MAGE, "TOP", 50, 0.1, 30), (AP_MAGE, "TOP", 53, 0.05, 30)])

    out = criteria.compute(agg, Draft("TOP", allies=[Pick(50, "JUNGLE"), Pick(53, "UTILITY")]))

    assert out.loc[AP_MAGE, "C"] == pytest.approx(0.15)
    assert out.loc[AD_TANK, "C"] == 0


def test_s_prefers_low_matchup_spread():
    out = criteria.compute(make_aggregates(), Draft("TOP"))

    assert out.loc[AP_TANK, "S"] > out.loc[AD_CARRY, "S"]


def test_d_personal_form_rewards_recent_wins_and_ignores_unplayed():
    profile = PlayerProfile(games=[PlayerGame(AP_MAGE, True, 2) for _ in range(8)]
                            + [PlayerGame(WEAK, False, 3) for _ in range(8)]
                            + [PlayerGame(AD_TANK, True, 365) for _ in range(8)])

    out = criteria.compute(make_aggregates(), Draft("TOP"), profile)

    assert out.loc[AP_MAGE, "D"] > 0.3
    assert out.loc[WEAK, "D"] < -0.3
    assert 0 < out.loc[AD_TANK, "D"] < 0.05  # a year old: almost no weight
    assert out.loc[AD_CARRY, "D"] == 0


def test_e_comfort_saturates_and_decays():
    profile = PlayerProfile(mastery={
        AD_TANK: Mastery(1_000_000, 0),
        AD_CARRY: Mastery(200_000, 0),
        AP_MAGE: Mastery(200_000, 365),
        AP_TANK: Mastery(1_000, 0),
    })

    out = criteria.compute(make_aggregates(), Draft("TOP"), profile)

    assert out.loc[AD_TANK, "E"] == pytest.approx(1.0)
    assert out.loc[AD_CARRY, "E"] == pytest.approx(1.0)
    assert out.loc[AP_MAGE, "E"] < 0.55
    assert 0 < out.loc[AP_TANK, "E"] < out.loc[AD_CARRY, "E"]
    assert out.loc[WEAK, "E"] == 0


def test_f_depends_on_candidate_and_favours_ap_in_all_ad_team():
    out = criteria.compute(make_aggregates(), Draft("TOP", allies=ALL_AD_TEAM))

    assert out["F"].nunique() > 1  # v1 bug: balance was identical for everybody
    assert out.loc[AP_TANK, "F"] > out.loc[AD_TANK, "F"]
    assert out.loc[AP_TANK, "F"] > out.loc[AP_MAGE, "F"]  # also brings frontline
    assert out["F"].idxmax() == AP_TANK


def test_f_is_zero_without_allies_and_grows_with_team():
    blind = criteria.compute(make_aggregates(), Draft("TOP"))
    one = criteria.compute(make_aggregates(), Draft("TOP", allies=ALL_AD_TEAM[:1]))
    four = criteria.compute(make_aggregates(), Draft("TOP", allies=ALL_AD_TEAM))

    assert (blind["F"] == 0).all()
    assert one["F"].abs().max() < four["F"].abs().max()


def test_no_missing_values_and_unknown_position_rejected():
    out = criteria.compute(make_aggregates(), Draft("TOP", allies=ALL_AD_TEAM))

    assert not out[criteria.CRITERIA].isna().any().any()
    with pytest.raises(ValueError):
        Draft("ADC")


def test_w_sums_win_criteria_with_fading_blind_safety():
    blind = criteria.compute(make_aggregates(), Draft("TOP"))
    row = blind.loc[AD_CARRY]

    assert row["W"] == pytest.approx(row["A"] + row["B"] + row["C"] + row["D"] + 0.5 * row["S"])
    known = criteria.compute(make_aggregates(), Draft("TOP", enemies=[Pick(50 + i, p) for i, p in
                             enumerate(["JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])] + [Pick(54, "TOP")]))
    assert known.loc[AD_CARRY, "W"] == pytest.approx(known.loc[AD_CARRY, ["A", "B", "C", "D"]].sum())
