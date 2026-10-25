"""Backtest tests. TEST DATA ONLY: synthetic matches on two fake patches."""

import pandas as pd
import pytest

from model import backtest
from pipeline import aggregate as agg
from pipeline.collect import RunStats, collect
from tests.match_factory import TEST_CHAMPION_IDS, make_match, with_participant
from tests.test_collect import FakeRiotClient, conn  # noqa: F401  (fixture)

TRAIN, TEST = "15.19", "15.20"


@pytest.fixture
def two_patch_db(conn):  # noqa: F811
    """60 matches on 15.19 and 40 on 15.20; TOP picks vary so rankings are not trivial."""
    matches = {}
    for i in range(100):
        match_id = f"EUN1_{i}"
        version = f"{TRAIN}.1.1" if i < 60 else f"{TEST}.1.1"
        m = make_match(match_id, blue_win=i % 3 != 0, gameVersion=version,
                       gameCreation=1_760_000_000_000 + i * 1000)
        m = with_participant(m, 0, championId=1 if i % 2 else 12)
        m = with_participant(m, 5, championId=6 if i % 4 else 13)
        matches[match_id] = m
    client = FakeRiotClient(matches, {"TEST-GOLD-I-a": list(matches)})
    collect(conn, client, TEST_CHAMPION_IDS, 1, tiers=["GOLD"], players_per_tier=1,
            matches_per_player=200, max_matches=200, start_time=None, stats=RunStats())
    return conn


def test_split_has_no_leakage_and_trains_on_older_patch(two_patch_db):
    split = backtest.load_split(two_patch_db)

    assert (split.train_patch, split.test_patch) == (TRAIN, TEST)
    assert len(split.train_ids) == 60 and len(split.test_ids) == 40
    assert not split.train_ids & split.test_ids
    aggregates = backtest.train_aggregates(split)
    assert aggregates.meta["current_patch"] == TRAIN
    assert aggregates.meta["matches_used"] == 60


def test_overlapping_split_is_refused():
    raw = pd.DataFrame({"match_id": ["a", "a"], "patch": ["1.1", "1.2"]})
    with pytest.raises(AssertionError):
        backtest.split_by_patch(raw, raw, raw, "1.1", "1.2")


def test_compute_matches_tables_written_by_aggregate(two_patch_db):
    tables, _ = agg.compute(agg.load_participants(two_patch_db))
    agg.aggregate(two_patch_db)
    stored = pd.read_sql_query("SELECT * FROM champion_role_stats", two_patch_db)

    pd.testing.assert_frame_equal(
        tables["champion_role_stats"].reset_index(drop=True), stored, check_dtype=False)


def test_run_reports_every_method(two_patch_db, tmp_path):
    out = tmp_path / "vysledky.md"
    result = backtest.run(two_patch_db, draft_count=12, use_v1=False, output=out, images=tmp_path / "img")

    methods = set(result["hits"]["method"])
    assert methods == {"v2", "nejvyšší vyhlazený winrate", "nejhranější v roli"}
    assert len(result["win"]["table"]) == 4
    assert result["win"]["matches"] == 40
    assert result["hits"]["coverage"].between(0, 1).all()
    assert (result["weights"]["cr"] < 0.1).all()
    text = out.read_text(encoding="utf-8")
    assert f"patche **{TRAIN}**" in text and "## Omezení" in text
    assert {p.name for p in (tmp_path / "img").iterdir()} == {"kalibrace.png", "hit-at-k.png", "smaa-stabilita.png"}


def test_prior_scale_changes_shrinkage(two_patch_db):
    split = backtest.load_split(two_patch_db)
    weak = backtest.train_aggregates(split, prior_scale=2.0).matchups["shift"].abs().max()
    strong = backtest.train_aggregates(split, prior_scale=0.5).matchups["shift"].abs().max()
    assert strong < weak
