"""explain CLI helpers. TEST DATA ONLY: synthetic aggregates from model_factory."""

import pytest

from model.explain import ChampionNames, build_draft, explain
from tests.model_factory import AD_CARRY, AD_TANK, FLEX, WEAK, make_aggregates

NAMES = {AD_TANK: "Test Tank", AD_CARRY: "Test Carry", 3: "Test Mage", 4: "Test AP Tank",
         WEAK: "Test Weak", FLEX: "Kog'Test", 50: "Test Jungler", 51: "Test Mid"}


@pytest.fixture
def agg():
    a = make_aggregates()
    a.names = NAMES
    return a


def test_names_ignore_case_and_punctuation():
    names = ChampionNames(NAMES)
    assert names.id("kogtest") == FLEX
    assert names.id("TEST tank") == AD_TANK
    assert names.pick("Test Jungler:jungle").position == "JUNGLE"


def test_unknown_name_suggests_close_match():
    with pytest.raises(SystemExit, match="Test Tank"):
        ChampionNames(NAMES).id("Test Tnak")


def test_invalid_draft_is_rejected():
    with pytest.raises(ValueError):
        build_draft(ChampionNames(NAMES), "TOP", allies=["Test Tank:TOP"])


def test_focus_outside_top_shows_rank_and_gap(agg):
    draft = build_draft(ChampionNames(NAMES), "TOP", allies=["Test Jungler:JUNGLE"])
    result = explain(agg, draft, WEAK)

    assert result["top"][0]["champion_id"] != WEAK
    focus = result["focus"]
    assert focus["available"] and focus["rank"] == focus["candidates"]  # weakest is last
    assert focus["gap_to_first_pp"]["A"] < 0
    assert 0.0 <= focus["top5_probability"] <= 1.0


def test_focus_matches_the_top_list_for_the_same_champion(agg):
    draft = build_draft(ChampionNames(NAMES), "TOP")
    result = explain(agg, draft, AD_TANK)

    in_top = next(c for c in result["top"] if c["champion_id"] == AD_TANK)
    assert result["focus"]["top5_probability"] == in_top["top5_probability"]
    assert result["focus"]["rank"] == in_top["rank"]


def test_focus_explains_unavailable_champions(agg):
    draft = build_draft(ChampionNames(NAMES), "TOP", bans=["Test Tank"])
    assert explain(agg, draft, AD_TANK)["focus"]["reason"] == "banned or already picked"
    off_role = explain(agg, draft, FLEX)["focus"]
    assert not off_role["available"] and "under 5%" in off_role["reason"]
