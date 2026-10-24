"""Quality report after each pipeline run: counts for the run plus sanity checks on the database."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path

# A blue-side winrate further than this many standard errors from 50 % is suspicious.
SANITY_Z = 3.0
MIN_MATCHES_FOR_SANITY = 100
MIN_CURRENT_PATCH_SHARE = 0.5


def build_report(conn, run_id: int, stats, requests_made: int, rate_limited: int) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    blue_wins = conn.execute("SELECT COALESCE(SUM(blue_win), 0) FROM matches").fetchone()[0]
    patches = dict(
        conn.execute(
            "SELECT patch, COUNT(*) FROM matches GROUP BY patch ORDER BY COUNT(*) DESC"
        ).fetchall()
    )
    tiers = dict(conn.execute("SELECT sampled_tier, COUNT(*) FROM matches GROUP BY sampled_tier"))
    quarantine_total = dict(conn.execute("SELECT reason, COUNT(*) FROM quarantine GROUP BY reason"))
    champions_seen = conn.execute("SELECT COUNT(DISTINCT champion_id) FROM participants").fetchone()[0]
    champions_known = conn.execute("SELECT COUNT(*) FROM champions").fetchone()[0]

    warnings = []
    blue_rate = blue_wins / total if total else None
    if total >= MIN_MATCHES_FOR_SANITY:
        se = math.sqrt(0.25 / total)
        if abs(blue_rate - 0.5) > SANITY_Z * se:
            warnings.append(
                f"blue side winrate {blue_rate:.1%} is more than {SANITY_Z:.0f} SE from 50 % (n={total})"
            )
    else:
        warnings.append(f"only {total} matches: sanity checks need at least {MIN_MATCHES_FOR_SANITY}")

    current_patch = _latest_patch(patches)
    if current_patch and patches[current_patch] / total < MIN_CURRENT_PATCH_SHARE:
        warnings.append(
            f"current patch {current_patch} is only {patches[current_patch] / total:.0%} of matches"
        )

    # Every match has exactly 5 winners; anything else means a broken insert.
    bad_results = conn.execute(
        "SELECT COUNT(*) FROM (SELECT match_id FROM participants GROUP BY match_id "
        "HAVING COUNT(*) != 10 OR SUM(win) != 5)"
    ).fetchone()[0]
    if bad_results:
        warnings.append(f"{bad_results} stored matches without 10 players / 5 winners")

    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run": {
            "players_sampled": stats.players_sampled,
            "players_processed": stats.players_processed,
            "match_ids_listed": stats.ids_listed,
            "duplicates_skipped": stats.duplicates_skipped,
            "not_found": stats.not_found,
            "downloaded": stats.downloaded,
            "stored": stats.stored,
            "quarantined": dict(stats.quarantined),
            "api_requests": requests_made,
            "rate_limited_429": rate_limited,
        },
        "database": {
            "matches": total,
            "quarantined": quarantine_total,
            "blue_winrate": round(blue_rate, 4) if blue_rate is not None else None,
            "current_patch": current_patch,
            "patches": patches,
            "tiers": tiers,
            "champions_seen": champions_seen,
            "champions_known": champions_known,
        },
        "warnings": warnings,
    }


def _latest_patch(patches: dict) -> str | None:
    if not patches:
        return None
    return max(patches, key=lambda p: tuple(int(x) for x in p.split(".") if x.isdigit()))


def save_report(conn, run_id: int, status: str, report: dict, db_path: str) -> Path:
    with conn:
        conn.execute(
            "UPDATE pipeline_runs SET finished_at = ?, status = ?, report = ? WHERE run_id = ?",
            (report["created_at"], status, json.dumps(report), run_id),
        )
    reports_dir = Path(db_path).parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"run_{run_id:04d}.md"
    path.write_text(to_markdown(report, status), encoding="utf-8")
    return path


def to_markdown(report: dict, status: str) -> str:
    run, database = report["run"], report["database"]
    quarantined = ", ".join(f"{k} {v}" for k, v in run["quarantined"].items()) or "none"
    lines = [
        f"# Data quality report, run {report['run_id']} ({status})",
        "",
        f"Created {report['created_at']}",
        "",
        "## This run",
        f"- players sampled / processed: {run['players_sampled']} / {run['players_processed']}",
        f"- match ids listed: {run['match_ids_listed']}, duplicates skipped: {run['duplicates_skipped']}",
        f"- downloaded: {run['downloaded']}, stored: {run['stored']}, not found: {run['not_found']}",
        f"- quarantined: {quarantined}",
        f"- API requests: {run['api_requests']}, 429 responses: {run['rate_limited_429']}",
        "",
        "## Database",
        f"- matches: {database['matches']}, quarantined: {sum(database['quarantined'].values())} "
        f"({', '.join(f'{k} {v}' for k, v in database['quarantined'].items()) or 'none'})",
        f"- blue side winrate: {_pct(database['blue_winrate'])}",
        f"- current patch: {database['current_patch']}; patches: "
        + (", ".join(f"{k} ({v})" for k, v in database["patches"].items()) or "none"),
        "- tiers: " + (", ".join(f"{k} {v}" for k, v in database["tiers"].items()) or "none"),
        f"- champions seen: {database['champions_seen']} of {database['champions_known']}",
        "",
        "## Warnings",
    ]
    lines += [f"- {w}" for w in report["warnings"]] or ["- none"]
    return "\n".join(lines) + "\n"


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.1%}"
