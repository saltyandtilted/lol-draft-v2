"""Print the pipeline state: unfinished runs, players per tier and the latest report.

Usage (from backend/): .venv\\Scripts\\python -m pipeline.status
"""

import argparse
from pathlib import Path

from app import db
from app.config import Config


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Show data pipeline status.")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        print(f"No database at {args.db}. Run pipeline.collect first.")
        return
    conn = db.connect(args.db)
    running = conn.execute(
        "SELECT run_id, started_at FROM pipeline_runs WHERE status = 'running'"
    ).fetchall()
    print("Runs marked running: " + (", ".join(f"{r[0]} (since {r[1]})" for r in running) or "none"))
    matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    quarantined = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    print(f"Matches: {matches}, quarantined: {quarantined}")
    print("Players per tier (total / pending):")
    for tier, total, pending in conn.execute(
        "SELECT tier, COUNT(*), SUM(matches_listed_at IS NULL) FROM players GROUP BY tier ORDER BY tier"
    ):
        print(f"  {tier}: {total} / {pending}")
    reports = sorted((Path(args.db).parent / "reports").glob("run_*.md"))
    print(f"Latest report: {reports[-1] if reports else 'none'}")
    conn.close()


if __name__ == "__main__":
    main()
