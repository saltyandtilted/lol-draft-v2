"""SQLite connection helpers and schema.

The schema is shared by the Flask app (reads) and the data pipeline (writes).
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Data Dragon champion list for the latest known version.
CREATE TABLE IF NOT EXISTS champions (
    champion_id INTEGER PRIMARY KEY,   -- numeric key used by match-v5
    champion_key TEXT NOT NULL,        -- e.g. "MonkeyKing"
    name        TEXT NOT NULL,         -- e.g. "Wukong"
    tags        TEXT NOT NULL,         -- JSON list, e.g. ["Fighter", "Tank"]
    ddragon_version TEXT NOT NULL
);

-- Players sampled from league-exp-v4. Only used to find matches; no player scores are stored.
CREATE TABLE IF NOT EXISTS players (
    puuid       TEXT PRIMARY KEY,
    platform    TEXT NOT NULL,
    tier        TEXT NOT NULL,
    division    TEXT NOT NULL,
    sampled_at  TEXT NOT NULL,
    matches_listed_at TEXT            -- NULL until the match history was listed
);

-- Matches that passed all download checks.
CREATE TABLE IF NOT EXISTS matches (
    match_id      TEXT PRIMARY KEY,
    platform      TEXT NOT NULL,
    queue_id      INTEGER NOT NULL,
    game_version  TEXT NOT NULL,
    patch         TEXT NOT NULL,       -- "15.20" from "15.20.712.3456"
    game_creation INTEGER NOT NULL,    -- epoch ms
    game_duration INTEGER NOT NULL,    -- seconds
    blue_win      INTEGER NOT NULL,    -- 1 if team 100 won
    sampled_tier  TEXT NOT NULL,       -- tier of the player whose history led to the match
    run_id        INTEGER NOT NULL,
    fetched_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    match_id    TEXT NOT NULL REFERENCES matches(match_id),
    team_id     INTEGER NOT NULL,      -- 100 blue, 200 red
    position    TEXT NOT NULL,         -- TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
    champion_id INTEGER NOT NULL,
    win         INTEGER NOT NULL,
    -- Per-player stats for the champion profile (criterion F). NULL until backfilled.
    physical_damage  INTEGER,         -- physicalDamageDealtToChampions
    magic_damage     INTEGER,         -- magicDamageDealtToChampions
    true_damage      INTEGER,         -- trueDamageDealtToChampions
    damage_taken     INTEGER,         -- totalDamageTaken
    damage_mitigated INTEGER,         -- damageSelfMitigated
    cc_time          INTEGER,         -- timeCCingOthers (seconds)
    PRIMARY KEY (match_id, team_id, position)
);

CREATE TABLE IF NOT EXISTS bans (
    match_id    TEXT NOT NULL REFERENCES matches(match_id),
    team_id     INTEGER NOT NULL,
    pick_turn   INTEGER NOT NULL,
    champion_id INTEGER NOT NULL,      -- -1 means no ban
    PRIMARY KEY (match_id, team_id, pick_turn)
);

-- Matches rejected by a check. Never dropped silently.
CREATE TABLE IF NOT EXISTS quarantine (
    match_id    TEXT PRIMARY KEY,
    reason      TEXT NOT NULL,         -- first failed check, e.g. "early_surrender"
    details     TEXT NOT NULL,         -- all failed checks, human readable
    game_version TEXT,
    run_id      INTEGER NOT NULL,
    quarantined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,         -- running, finished, interrupted, failed
    params      TEXT NOT NULL,         -- JSON
    report      TEXT                   -- JSON quality report
);

CREATE INDEX IF NOT EXISTS idx_matches_patch ON matches(patch);
CREATE INDEX IF NOT EXISTS idx_participants_champion ON participants(champion_id, position);
"""


# Columns added after schema v2: (table, column, type). Added with ALTER TABLE when missing.
MIGRATION_COLUMNS = [
    ("participants", "physical_damage", "INTEGER"),
    ("participants", "magic_damage", "INTEGER"),
    ("participants", "true_damage", "INTEGER"),
    ("participants", "damage_taken", "INTEGER"),
    ("participants", "damage_mitigated", "INTEGER"),
    ("participants", "cc_time", "INTEGER"),
]


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _add_missing_columns(conn)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, sql_type in MIGRATION_COLUMNS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")


def schema_version(db_path: str) -> str | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return row["value"] if row else None
