"""Schema migration and stats backfill. TEST DATA ONLY, no network."""

import sqlite3

from app import db
from pipeline.backfill import backfill, matches_without_stats
from pipeline.collect import RunStats, collect
from tests.match_factory import TEST_CHAMPION_IDS, make_match
from tests.test_collect import FakeRiotClient, conn  # noqa: F401  (fixture)


def test_init_db_adds_stats_columns_to_v2_database(tmp_path):
    path = str(tmp_path / "v2.db")
    legacy = sqlite3.connect(path)
    legacy.execute(
        "CREATE TABLE participants (match_id TEXT NOT NULL, team_id INTEGER NOT NULL, "
        "position TEXT NOT NULL, champion_id INTEGER NOT NULL, win INTEGER NOT NULL, "
        "PRIMARY KEY (match_id, team_id, position))"
    )
    legacy.execute("INSERT INTO participants VALUES ('EUN1_OLD', 100, 'TOP', 1, 1)")
    legacy.commit()
    legacy.close()

    db.init_db(path)

    conn = db.connect(path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(participants)")}
    assert {"physical_damage", "cc_time"} <= columns
    assert conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0] == 1
    conn.close()


def test_collect_stores_stats(conn):  # noqa: F811
    client = FakeRiotClient({"EUN1_1": make_match("EUN1_1")}, {"TEST-GOLD-I-a": ["EUN1_1"]})
    collect(
        conn, client, TEST_CHAMPION_IDS, 1, tiers=["GOLD"], players_per_tier=1,
        matches_per_player=5, max_matches=5, start_time=None, stats=RunStats(),
    )

    row = conn.execute(
        "SELECT physical_damage, cc_time FROM participants WHERE team_id = 100 AND position = 'UTILITY'"
    ).fetchone()
    assert tuple(row) == (20000, 40)
    assert matches_without_stats(conn) == []


def test_backfill_fills_missing_stats_once(conn):  # noqa: F811
    client = FakeRiotClient({"EUN1_1": make_match("EUN1_1")}, {"TEST-GOLD-I-a": ["EUN1_1"]})
    collect(
        conn, client, TEST_CHAMPION_IDS, 1, tiers=["GOLD"], players_per_tier=1,
        matches_per_player=5, max_matches=5, start_time=None, stats=RunStats(),
    )
    with conn:
        conn.execute("UPDATE participants SET physical_damage = NULL, cc_time = NULL")
    assert matches_without_stats(conn) == ["EUN1_1"]

    first = backfill(conn, client)
    second = backfill(conn, client)

    assert first["updated"] == 1
    assert second["updated"] == 0
    assert conn.execute("SELECT SUM(cc_time) FROM participants").fetchone()[0] == 2 * (4 * 10 + 40)
