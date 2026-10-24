"""Fill participant stats for matches stored before schema v3.

Usage (from backend/):
    .venv\\Scripts\\python -m pipeline.backfill

Downloads each match whose participants have no stats yet and updates the stats columns.
Safe to interrupt: every match is committed on its own and finished matches are not revisited.
"""

import argparse
import logging

from app import db
from app.config import Config

from .collect import participant_stats
from .riot_client import RiotClient, RiotKeyError
from .schemas import Match

log = logging.getLogger("pipeline")


def matches_without_stats(conn) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT match_id FROM participants WHERE physical_damage IS NULL ORDER BY match_id"
        )
    ]


def backfill(conn, client, limit: int | None = None) -> dict:
    counts = {"updated": 0, "not_found": 0, "schema_error": 0}
    for match_id in matches_without_stats(conn)[:limit]:
        raw = client.match(match_id)
        if raw is None:
            counts["not_found"] += 1
            continue
        try:
            match = Match.model_validate(raw)
        except ValueError:
            counts["schema_error"] += 1
            continue
        with conn:
            conn.executemany(
                "UPDATE participants SET physical_damage = ?, magic_damage = ?, true_damage = ?, "
                "damage_taken = ?, damage_mitigated = ?, cc_time = ? "
                "WHERE match_id = ? AND team_id = ? AND position = ?",
                [
                    participant_stats(p) + (match_id, p.teamId, p.teamPosition)
                    for p in match.info.participants
                ],
            )
        counts["updated"] += 1
        if counts["updated"] % 50 == 0:
            log.info("%d matches backfilled", counts["updated"])
    return counts


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Backfill participant stats.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    args = parser.parse_args(argv)
    db.init_db(args.db)
    conn = db.connect(args.db)
    status = 0
    counts = {}
    try:
        client = RiotClient(Config.RIOT_API_KEY, Config.DEFAULT_PLATFORM, Config.DEFAULT_REGION)
        counts = backfill(conn, client, args.limit)
    except KeyboardInterrupt:
        log.warning("Interrupted. Run again to continue.")
        status = 1
    except RiotKeyError as exc:
        log.error("%s", exc)
        status = 1
    remaining = len(matches_without_stats(conn))
    print(f"Backfill: {counts}, matches still without stats: {remaining}")
    conn.close()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
