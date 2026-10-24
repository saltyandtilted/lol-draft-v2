"""Collect ranked solo matches from the Riot API into SQLite.

Usage (from backend/):
    .venv\\Scripts\\python -m pipeline.collect --max-matches 20

The run is safe to interrupt (Ctrl+C) and restart: every match is committed on its own,
match ids already stored or quarantined are skipped before downloading, and a player is
marked done only after all of their listed matches were processed.
"""

import argparse
import json
import logging
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import zip_longest

from app import db
from app.config import Config

from . import ddragon, report
from .quality import patch_of, validate_match
from .riot_client import RiotClient, RiotKeyError
from .schemas import LeagueEntry, Match

log = logging.getLogger("pipeline")

TIERS = [
    "IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD",
    "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER",
]
APEX_TIERS = {"MASTER", "GRANDMASTER", "CHALLENGER"}
DIVISIONS = ["I", "II", "III", "IV"]


@dataclass
class RunStats:
    players_sampled: int = 0
    players_processed: int = 0
    ids_listed: int = 0
    duplicates_skipped: int = 0
    not_found: int = 0
    stored: int = 0
    quarantined: Counter = field(default_factory=Counter)

    @property
    def downloaded(self) -> int:
        return self.stored + sum(self.quarantined.values())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- Data Dragon --------------------------------------------------------------------------------


def refresh_champions(conn: sqlite3.Connection) -> str:
    version = ddragon.latest_version()
    row = conn.execute("SELECT ddragon_version FROM champions LIMIT 1").fetchone()
    if row is None or row[0] != version:
        champions = ddragon.fetch_champions(version)
        with conn:
            ddragon.store_champions(conn, champions, version)
        log.info("Data Dragon %s: %d champions stored", version, len(champions))
    return version


# --- Player sampling ----------------------------------------------------------------------------


def sample_players(conn, client: RiotClient, tiers: list[str], players_per_tier: int, stats: RunStats):
    """Top up every tier to `players_per_tier` pending players, spread over its divisions.

    Counting only players whose history is not listed yet makes every new run sample fresh players.
    """
    for tier in tiers:
        have = conn.execute(
            "SELECT COUNT(*) FROM players WHERE tier = ? AND matches_listed_at IS NULL", (tier,)
        ).fetchone()[0]
        missing = players_per_tier - have
        if missing <= 0:
            continue
        divisions = ["I"] if tier in APEX_TIERS else DIVISIONS
        per_division = -(-missing // len(divisions))  # ceil
        for division in divisions:
            if missing <= 0:
                break
            entries = [LeagueEntry.model_validate(e) for e in client.league_entries(tier, division)]
            fresh = [e for e in entries if not _player_known(conn, e.puuid)]
            fresh = fresh[: min(per_division, missing)]
            missing -= len(fresh)
            with conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO players (puuid, platform, tier, division, sampled_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [(e.puuid, client.platform, e.tier, e.rank, now_iso()) for e in fresh],
                )
            stats.players_sampled += len(fresh)
        log.info("Sampled players for %s", tier)


def _player_known(conn, puuid: str) -> bool:
    return conn.execute("SELECT 1 FROM players WHERE puuid = ?", (puuid,)).fetchone() is not None


def pending_players(conn, tiers: list[str]) -> list[sqlite3.Row]:
    """Players whose history is not listed yet, interleaved by tier for a balanced sample."""
    by_tier = [
        conn.execute(
            "SELECT puuid, tier FROM players WHERE tier = ? AND matches_listed_at IS NULL "
            "ORDER BY sampled_at, puuid",
            (tier,),
        ).fetchall()
        for tier in tiers
    ]
    return [p for group in zip_longest(*by_tier) for p in group if p is not None]


# --- Matches ------------------------------------------------------------------------------------


def match_known(conn, match_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM matches WHERE match_id = ? UNION ALL "
            "SELECT 1 FROM quarantine WHERE match_id = ?",
            (match_id, match_id),
        ).fetchone()
        is not None
    )


def participant_stats(p) -> tuple[int, ...]:
    """Values for the participants stats columns, in schema order."""
    return (
        p.physicalDamageDealtToChampions,
        p.magicDamageDealtToChampions,
        p.trueDamageDealtToChampions,
        p.totalDamageTaken,
        p.damageSelfMitigated,
        p.timeCCingOthers,
    )


def store_match(conn, match: Match, platform: str, sampled_tier: str, run_id: int) -> None:
    info = match.info
    # check_completeness guarantees exactly one winning team.
    blue_win = any(p.win for p in info.participants if p.teamId == 100)
    with conn:
        conn.execute(
            "INSERT INTO matches (match_id, platform, queue_id, game_version, patch, game_creation, "
            "game_duration, blue_win, sampled_tier, run_id, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                match.metadata.matchId, platform, info.queueId, info.gameVersion,
                patch_of(info.gameVersion), info.gameCreation, info.duration_seconds,
                int(blue_win), sampled_tier, run_id, now_iso(),
            ),
        )
        conn.executemany(
            "INSERT INTO participants (match_id, team_id, position, champion_id, win, "
            "physical_damage, magic_damage, true_damage, damage_taken, damage_mitigated, cc_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (match.metadata.matchId, p.teamId, p.teamPosition, p.championId, int(p.win))
                + participant_stats(p)
                for p in info.participants
            ],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO bans (match_id, team_id, pick_turn, champion_id) "
            "VALUES (?, ?, ?, ?)",
            [
                (match.metadata.matchId, t.teamId, b.pickTurn, b.championId)
                for t in info.teams
                for b in t.bans
            ],
        )


def quarantine_match(conn, match_id: str, problems, game_version: str | None, run_id: int) -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO quarantine "
            "(match_id, reason, details, game_version, run_id, quarantined_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                match_id,
                problems[0][0],
                "; ".join(f"{reason}: {detail}" for reason, detail in problems),
                game_version,
                run_id,
                now_iso(),
            ),
        )


def process_match_id(conn, client, match_id, sampled_tier, known_ids, run_id, stats: RunStats):
    if match_known(conn, match_id):
        stats.duplicates_skipped += 1
        return
    raw = client.match(match_id)
    if raw is None:
        stats.not_found += 1
        return
    match, problems = validate_match(raw, known_ids)
    if problems:
        version = match.info.gameVersion if match else None
        quarantine_match(conn, match_id, problems, version, run_id)
        stats.quarantined[problems[0][0]] += 1
    else:
        store_match(conn, match, client.platform, sampled_tier, run_id)
        stats.stored += 1


def collect(
    conn,
    client,
    known_ids: set[int],
    run_id: int,
    *,
    tiers: list[str],
    players_per_tier: int,
    matches_per_player: int,
    max_matches: int,
    start_time: int | None,
    stats: RunStats,
) -> None:
    sample_players(conn, client, tiers, players_per_tier, stats)
    started = time.monotonic()
    last_logged = 0
    for player in pending_players(conn, tiers):
        if stats.downloaded >= max_matches:
            break
        ids = client.match_ids(player["puuid"], count=matches_per_player, start_time=start_time)
        stats.ids_listed += len(ids)
        for match_id in ids:
            if stats.downloaded >= max_matches:
                break
            process_match_id(conn, client, match_id, player["tier"], known_ids, run_id, stats)
            if stats.downloaded % 25 == 0 and stats.downloaded != last_logged:
                last_logged = stats.downloaded
                elapsed = time.monotonic() - started
                log.info(
                    "%d downloaded (%d stored, %d quarantined, %d duplicates) in %.0f s",
                    stats.downloaded, stats.stored, sum(stats.quarantined.values()),
                    stats.duplicates_skipped, elapsed,
                )
        else:
            # All listed matches processed: the player will not be revisited.
            with conn:
                conn.execute(
                    "UPDATE players SET matches_listed_at = ? WHERE puuid = ?",
                    (now_iso(), player["puuid"]),
                )
            stats.players_processed += 1


# --- Entry point --------------------------------------------------------------------------------


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Collect ranked solo matches into SQLite.")
    parser.add_argument("--max-matches", type=int, default=20, help="match details to download")
    parser.add_argument("--tiers", nargs="+", default=TIERS, choices=TIERS)
    parser.add_argument(
        "--players-per-tier", type=int, default=5, help="new (not yet processed) players per tier"
    )
    parser.add_argument("--matches-per-player", type=int, default=20)
    parser.add_argument("--days", type=int, default=14, help="only matches from the last N days")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    db.init_db(args.db)
    conn = db.connect(args.db)
    params = {k: v for k, v in vars(args).items() if k != "db"}
    with conn:
        run_id = conn.execute(
            "INSERT INTO pipeline_runs (started_at, status, params) VALUES (?, 'running', ?)",
            (now_iso(), json.dumps(params)),
        ).lastrowid

    stats = RunStats()
    status = "finished"
    client = None
    try:
        client = RiotClient(Config.RIOT_API_KEY, Config.DEFAULT_PLATFORM, Config.DEFAULT_REGION)
        refresh_champions(conn)
        start_time = int(time.time()) - args.days * 86400 if args.days else None
        collect(
            conn, client, ddragon.known_champion_ids(conn), run_id,
            tiers=args.tiers, players_per_tier=args.players_per_tier,
            matches_per_player=args.matches_per_player, max_matches=args.max_matches,
            start_time=start_time, stats=stats,
        )
    except KeyboardInterrupt:
        status = "interrupted"
        log.warning("Interrupted. Stored matches are kept; run again to continue.")
    except RiotKeyError as exc:
        status = "failed"
        log.error("%s", exc)

    requests_made = client.request_count if client else 0
    rate_limited = client.rate_limited_count if client else 0
    result = report.build_report(conn, run_id, stats, requests_made, rate_limited)
    path = report.save_report(conn, run_id, status, result, args.db)
    print(report.to_markdown(result, status))
    print(f"Report saved to {path}")
    conn.close()
    return 0 if status == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
