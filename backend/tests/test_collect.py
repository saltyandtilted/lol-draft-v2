"""Collector tests with a fake Riot client. TEST DATA ONLY, no network."""

import pytest

from app import db
from pipeline import ddragon, report
from pipeline.collect import RunStats, collect, sample_players
from tests.match_factory import TEST_CHAMPION_IDS, make_match, with_participant


class FakeRiotClient:
    platform = "eun1"

    def __init__(self, matches: dict, histories: dict, interrupt_after: int | None = None):
        self.matches = matches
        self.histories = histories
        self.interrupt_after = interrupt_after
        self.match_calls = []

    def league_entries(self, tier, division, page=1):
        return [
            {"puuid": puuid, "tier": tier, "rank": division}
            for puuid in self.histories
            if puuid.startswith(f"TEST-{tier}-{division}-")
        ]

    def match_ids(self, puuid, count=20, start_time=None):
        return self.histories[puuid][:count]

    def match(self, match_id):
        if self.interrupt_after is not None and len(self.match_calls) >= self.interrupt_after:
            raise KeyboardInterrupt
        self.match_calls.append(match_id)
        return self.matches.get(match_id)


def remake(match_id):
    return with_participant(make_match(match_id, gameDuration=180), 0, gameEndedInEarlySurrender=True)


@pytest.fixture
def conn(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    connection = db.connect(path)
    champions = [
        {"champion_id": i, "champion_key": f"Test{i}", "name": f"Test {i}", "tags": ["Fighter"]}
        for i in TEST_CHAMPION_IDS
    ]
    with connection:
        ddragon.store_champions(connection, champions, "test-version")
    yield connection
    connection.close()


def scenario(interrupt_after=None):
    matches = {f"EUN1_{i}": make_match(f"EUN1_{i}", blue_win=i % 2 == 0) for i in range(1, 6)}
    matches["EUN1_REMAKE"] = remake("EUN1_REMAKE")
    matches["EUN1_FLEX"] = make_match("EUN1_FLEX", queueId=440)
    histories = {
        # Two players share EUN1_2 and EUN1_3: the second copy must be skipped, not downloaded.
        "TEST-GOLD-I-a": ["EUN1_1", "EUN1_2", "EUN1_3", "EUN1_REMAKE"],
        "TEST-GOLD-II-b": ["EUN1_2", "EUN1_3", "EUN1_4", "EUN1_FLEX", "EUN1_MISSING"],
        "TEST-SILVER-I-c": ["EUN1_5", "EUN1_1"],
    }
    return FakeRiotClient(matches, histories, interrupt_after)


def run_collect(conn, client, run_id=1, max_matches=100):
    stats = RunStats()
    collect(
        conn, client, TEST_CHAMPION_IDS, run_id,
        tiers=["GOLD", "SILVER"], players_per_tier=4, matches_per_player=20,
        max_matches=max_matches, start_time=None, stats=stats,
    )
    return stats


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_collect_stores_clean_matches_and_quarantines_bad_ones(conn):
    stats = run_collect(conn, scenario())

    assert stats.stored == 5
    assert stats.quarantined == {"early_surrender": 1, "wrong_queue": 1}
    assert stats.duplicates_skipped == 3
    assert stats.not_found == 1
    assert count(conn, "matches") == 5
    assert count(conn, "participants") == 50
    reasons = dict(conn.execute("SELECT match_id, reason FROM quarantine"))
    assert reasons == {"EUN1_REMAKE": "early_surrender", "EUN1_FLEX": "wrong_queue"}


def test_duplicates_are_never_downloaded_twice(conn):
    client = scenario()
    run_collect(conn, client)

    assert len(client.match_calls) == len(set(client.match_calls))


def test_second_run_adds_nothing(conn):
    run_collect(conn, scenario())
    client = scenario()
    stats = run_collect(conn, client, run_id=2)

    assert stats.downloaded == 0
    assert client.match_calls == []
    assert count(conn, "matches") == 5


def test_interrupted_run_resumes_without_duplicates(conn):
    with pytest.raises(KeyboardInterrupt):
        run_collect(conn, scenario(interrupt_after=2))
    assert count(conn, "matches") == 2

    stats = run_collect(conn, scenario(), run_id=2)

    assert count(conn, "matches") == 5
    assert stats.stored == 3
    assert count(conn, "quarantine") == 2


def test_max_matches_limits_downloads(conn):
    stats = run_collect(conn, scenario(), max_matches=3)

    assert stats.downloaded == 3


def test_report_counts_and_warnings(conn):
    stats = run_collect(conn, scenario())
    result = report.build_report(conn, 1, stats, requests_made=12, rate_limited=0)

    assert result["database"]["matches"] == 5
    assert result["database"]["quarantined"] == {"early_surrender": 1, "wrong_queue": 1}
    assert result["database"]["current_patch"] == "15.20"
    assert any("sanity checks need" in w for w in result["warnings"])
    assert "early_surrender 1" in report.to_markdown(result, "finished")


def test_report_warns_about_blue_side_imbalance(conn):
    client = FakeRiotClient(
        {f"EUN1_{i}": make_match(f"EUN1_{i}", blue_win=True) for i in range(150)},
        {"TEST-GOLD-I-a": [f"EUN1_{i}" for i in range(150)]},
    )
    stats = RunStats()
    collect(
        conn, client, TEST_CHAMPION_IDS, 1, tiers=["GOLD"], players_per_tier=1,
        matches_per_player=200, max_matches=200, start_time=None, stats=stats,
    )
    result = report.build_report(conn, 1, stats, requests_made=0, rate_limited=0)

    assert any("blue side winrate" in w for w in result["warnings"])


def test_sampling_does_not_overshoot_players_per_tier(conn):
    histories = {f"TEST-GOLD-{d}-{i}": [] for d in ("I", "II", "III", "IV") for i in range(3)}
    stats = RunStats()
    sample_players(conn, FakeRiotClient({}, histories), ["GOLD"], 2, stats)

    assert stats.players_sampled == 2
    assert count(conn, "players") == 2


def test_next_run_samples_new_players(conn):
    divisions = ("I", "II", "III", "IV")
    histories = {f"TEST-GOLD-{d}-1": [] for d in divisions}
    client = FakeRiotClient({}, histories)
    run_collect(conn, client)
    assert count(conn, "players") == 4

    histories.update({f"TEST-GOLD-{d}-2": [] for d in divisions})
    run_collect(conn, client, run_id=2)

    assert count(conn, "players") == 8


def test_status_prints_summary(conn, tmp_path, capsys):
    from pipeline import status

    run_collect(conn, scenario())
    status.main(["--db", str(tmp_path / "test.db")])

    out = capsys.readouterr().out
    assert "Matches: 5, quarantined: 2" in out
    assert "GOLD: 2 / 0" in out
