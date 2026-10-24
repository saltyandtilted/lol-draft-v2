"""Aggregate stored matches into the tables the model reads.

Usage (from backend/):
    .venv\\Scripts\\python -m pipeline.aggregate

All tables are rebuilt from scratch on every run:
- champion_role_stats: strength in a role (criterion A), empirical Bayes smoothed
- matchup_stats: shift in log-odds against an enemy champion (criterion B)
- duo_stats: shift in log-odds with an allied champion (criterion C)
- champion_profile: damage type, frontline and CC per minute (criterion F)
- aggregate_meta: patch, data date and quality summary
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import db
from app.config import Config

# Weight of matches by patch age: current patch 1.0, previous 0.5, older ones are not used.
PATCH_WEIGHTS = (1.0, 0.5)
MIN_GAMES_CHAMPION = 20
MIN_GAMES_PAIR = 30
# Prior SD of matchup and duo shifts in log-odds: how large such effects realistically are.
# A lane matchup rarely moves the win chance by more than ~4 pp, other pairs much less.
# Prior precision 1/sd^2 equals k/4 "games" of shrinkage: shift = n / (n + k) * raw for p = 0.5.
PRIOR_SD = {"lane": 0.15, "off_lane": 0.05, "duo": 0.07}
# Lower bound for the between-champion SD of win rates in the empirical Bayes prior.
# Champion win rates in a role typically spread by 2-3 percentage points; with little data
# the method-of-moments estimate can collapse to 0 and would erase every difference.
MIN_PRIOR_SD = 0.02
MIN_CURRENT_PATCH_SHARE = 0.5
# Matchup spread of rarely played champions is shrunk towards the role mean with this many games.
# Without it, few games -> few shrunk matchups -> small spread, so "no data" looked like "safe".
SPREAD_PRIOR_GAMES = 100
Z_90 = 1.645


def logit(p):
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def patch_key(patch: str) -> tuple[int, ...]:
    return tuple(int(x) for x in patch.split(".") if x.isdigit())


# --- Loading ------------------------------------------------------------------------------------


def load_participants(conn) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT p.match_id, p.team_id, p.position, p.champion_id, p.win, "
        "p.physical_damage, p.magic_damage, p.true_damage, p.damage_taken, p.damage_mitigated, "
        "p.cc_time, m.patch, m.game_duration "
        "FROM participants p JOIN matches m ON m.match_id = p.match_id",
        conn,
    )
    return df


def add_patch_weights(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Add column `w` by patch age and drop patches older than PATCH_WEIGHTS covers."""
    patches = sorted(df["patch"].unique(), key=patch_key, reverse=True)[: len(PATCH_WEIGHTS)]
    weights = dict(zip(patches, PATCH_WEIGHTS))
    df = df[df["patch"].isin(weights)].copy()
    df["w"] = df["patch"].map(weights)
    return df, patches


# --- Criterion A: champion strength in a role ---------------------------------------------------


def champion_role_stats(df: pd.DataFrame) -> pd.DataFrame:
    df = df.assign(w_win=df["w"] * df["win"])
    grouped = (
        df.groupby(["champion_id", "position"])
        .agg(games=("win", "size"), w_games=("w", "sum"), w_wins=("w_win", "sum"))
        .reset_index()
    )
    champion_total = grouped.groupby("champion_id")["w_games"].transform("sum")
    grouped["role_share"] = grouped["w_games"] / champion_total

    parts = []
    for position, role in grouped.groupby("position"):
        parts.append(_empirical_bayes(role.copy()))
    out = pd.concat(parts, ignore_index=True)
    out["low_data"] = out["games"] < MIN_GAMES_CHAMPION
    return out


def _empirical_bayes(role: pd.DataFrame) -> pd.DataFrame:
    """Beta-binomial empirical Bayes within one role (method of moments)."""
    n = role["w_games"].to_numpy()
    wins = role["w_wins"].to_numpy()
    mean = wins.sum() / n.sum()
    rates = wins / n
    observed_var = np.average((rates - mean) ** 2, weights=n)
    noise_var = np.average(mean * (1 - mean) / n, weights=n)
    prior_var = max(observed_var - noise_var, MIN_PRIOR_SD**2)
    # Beta(a, b) with the given mean and variance: a + b = m(1-m)/var - 1.
    strength = max(mean * (1 - mean) / prior_var - 1, 1.0)
    alpha, beta = mean * strength, (1 - mean) * strength

    post_n = alpha + beta + n
    posterior = (alpha + wins) / post_n
    sd = np.sqrt(posterior * (1 - posterior) / (post_n + 1))
    role["role_mean"] = mean
    role["prior_strength"] = strength
    role["posterior_mean"] = posterior
    role["ci_low"] = np.clip(posterior - Z_90 * sd, 0.001, 0.999)
    role["ci_high"] = np.clip(posterior + Z_90 * sd, 0.001, 0.999)
    role["dev_logodds"] = logit(posterior) - logit(mean)
    return role


# --- Criteria B and C: matchups and duos --------------------------------------------------------


def _pairs(df: pd.DataFrame, same_team: bool) -> pd.DataFrame:
    left = df[["match_id", "team_id", "position", "champion_id", "win", "w", "dev"]]
    right = left.rename(
        columns={
            "team_id": "o_team", "position": "o_position", "champion_id": "o_champion",
            "win": "o_win", "w": "o_w", "dev": "o_dev",
        }
    )
    pairs = left.merge(right, on="match_id")
    if same_team:
        pairs = pairs[(pairs["team_id"] == pairs["o_team"]) & (pairs["position"] != pairs["o_position"])]
    else:
        pairs = pairs[pairs["team_id"] != pairs["o_team"]]
    return pairs


def prior_games(kind: str) -> float:
    """Shrinkage strength k in games for a prior SD (k/4 = 1/sd^2)."""
    return 4 / PRIOR_SD[kind] ** 2


def _shift(pairs: pd.DataFrame, keys: list[str], prior_precision) -> pd.DataFrame:
    """Log-odds shift of the win rate against the expectation `pairs.expected`.

    One Newton step from shift 0 with a normal prior N(0, sd^2):
    sum(win - p) / (sum(p(1-p)) + 1/sd^2). With p = 0.5 this equals n / (n + k) times the raw
    log-odds deviation, k = 4 / sd^2. `prior_precision` is a number or a Series aligned with `pairs`.
    """
    p = sigmoid(pairs["expected"])
    pairs = pairs.assign(resid=pairs["w"] * (pairs["win"] - p), info=pairs["w"] * p * (1 - p),
                         precision=prior_precision)
    out = (
        pairs.groupby(keys)
        .agg(games=("win", "size"), w_games=("w", "sum"), resid=("resid", "sum"), info=("info", "sum"),
             precision=("precision", "first"))
        .reset_index()
    )
    out["shift"] = out["resid"] / (out["info"] + out["precision"])
    out = out.drop(columns="precision")
    out["low_data"] = out["games"] < MIN_GAMES_PAIR
    return out.drop(columns=["resid", "info"])


def matchup_stats(df: pd.DataFrame) -> pd.DataFrame:
    pairs = _pairs(df, same_team=False)
    pairs = pairs.assign(
        expected=pairs["dev"] - pairs["o_dev"],
        lane=(pairs["position"] == pairs["o_position"]).astype(int),
    )
    precision = np.where(pairs["lane"] == 1, 1 / PRIOR_SD["lane"] ** 2, 1 / PRIOR_SD["off_lane"] ** 2)
    out = _shift(pairs, ["champion_id", "position", "o_champion", "lane"], precision)
    return out.rename(columns={"o_champion": "enemy_champion_id"})


def duo_stats(df: pd.DataFrame) -> pd.DataFrame:
    pairs = _pairs(df, same_team=True)
    pairs = pairs.assign(expected=pairs["dev"] + pairs["o_dev"])
    out = _shift(pairs, ["champion_id", "position", "o_champion"], 1 / PRIOR_SD["duo"] ** 2)
    return out.rename(columns={"o_champion": "ally_champion_id"})


def matchup_spread(matchups: pd.DataFrame) -> pd.DataFrame:
    """Root mean square of lane matchup shifts: how much a champion depends on the matchup."""
    lane = matchups[matchups["lane"] == 1]
    spread = lane.groupby(["champion_id", "position"]).apply(
        lambda g: float(np.sqrt(np.average(g["shift"] ** 2, weights=g["w_games"]))),
        include_groups=False,
    )
    return spread.rename("matchup_spread").reset_index()


def smooth_spread(champions: pd.DataFrame) -> pd.Series:
    """Blend each champion's matchup spread with its role's games-weighted mean spread."""
    spread = champions["matchup_spread"]
    known = spread.notna()
    role_mean = champions[known].groupby("position").apply(
        lambda g: float(np.average(g["matchup_spread"], weights=g["w_games"])), include_groups=False
    )
    prior = champions["position"].map(role_mean).fillna(0.0)
    n = champions["games"]
    return (n * spread.fillna(prior) + SPREAD_PRIOR_GAMES * prior) / (n + SPREAD_PRIOR_GAMES)


# --- Criterion F: champion profile --------------------------------------------------------------


def champion_profile(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.dropna(subset=["physical_damage", "magic_damage", "true_damage"]).copy()
    stats["minutes"] = stats["game_duration"] / 60
    stats["damage"] = stats["physical_damage"] + stats["magic_damage"] + stats["true_damage"]
    stats["tanked"] = stats["damage_taken"] + stats["damage_mitigated"]

    def summarize(group_keys):
        g = stats.groupby(group_keys).agg(
            games=("win", "size"),
            physical=("physical_damage", "sum"),
            damage=("damage", "sum"),
            tanked=("tanked", "sum"),
            cc=("cc_time", "sum"),
            minutes=("minutes", "sum"),
        )
        g["physical_share"] = g["physical"] / g["damage"].where(g["damage"] > 0)
        g["damage_per_min"] = g["damage"] / g["minutes"]
        g["tanked_per_min"] = g["tanked"] / g["minutes"]
        g["cc_per_min"] = g["cc"] / g["minutes"]
        return g.drop(columns=["physical", "damage", "tanked", "cc", "minutes"]).reset_index()

    by_role = summarize(["champion_id", "position"])
    overall = summarize(["champion_id"]).assign(position="ALL")
    profile = pd.concat([by_role, overall], ignore_index=True)
    return profile.dropna(subset=["physical_share"])


# --- Orchestration ------------------------------------------------------------------------------


def aggregate(conn) -> dict:
    raw = load_participants(conn)
    if raw.empty:
        raise ValueError("no matches in the database, run pipeline.collect first")
    df, patches = add_patch_weights(raw)

    champions = champion_role_stats(df)
    dev = champions.set_index(["champion_id", "position"])["dev_logodds"]
    df["dev"] = dev.reindex(pd.MultiIndex.from_frame(df[["champion_id", "position"]])).to_numpy()

    matchups = matchup_stats(df)
    duos = duo_stats(df)
    champions = champions.merge(matchup_spread(matchups), on=["champion_id", "position"], how="left")
    champions["matchup_spread"] = smooth_spread(champions)
    profile = champion_profile(df)

    tables = {
        "champion_role_stats": champions,
        "matchup_stats": matchups,
        "duo_stats": duos,
        "champion_profile": profile,
    }
    for name, table in tables.items():
        if table.isna().any().any():
            raise ValueError(f"{name} contains missing values: {table.columns[table.isna().any()].tolist()}")

    summary = _summary(raw, df, patches, champions, matchups, duos, profile)
    with conn:
        for name, table in tables.items():
            table.to_sql(name, conn, if_exists="replace", index=False)
        conn.execute("DROP TABLE IF EXISTS aggregate_meta")
        conn.execute("CREATE TABLE aggregate_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.executemany(
            "INSERT INTO aggregate_meta VALUES (?, ?)",
            [(k, json.dumps(v)) for k, v in summary.items()],
        )
    return summary


def _summary(raw, df, patches, champions, matchups, duos, profile) -> dict:
    current = patches[0]
    current_share = float((raw["patch"] == current).mean())
    warnings = []
    if current_share < MIN_CURRENT_PATCH_SHARE:
        warnings.append(f"current patch {current} is only {current_share:.0%} of participant rows")
    # Smoothed strengths should average to ~0 within each role.
    role_means = champions.groupby("position").apply(
        lambda g: float(np.average(g["dev_logodds"], weights=g["w_games"])), include_groups=False
    )
    off = role_means[role_means.abs() > 0.02]
    if not off.empty:
        warnings.append(f"mean dev_logodds not ~0 in roles: {off.round(3).to_dict()}")
    missing_stats = int(raw["physical_damage"].isna().sum())
    if missing_stats:
        warnings.append(f"{missing_stats} participant rows without stats; run pipeline.backfill")
    return {
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier_group": "ALL",
        "current_patch": current,
        "patches_used": dict(zip(patches, PATCH_WEIGHTS)),
        "matches_used": int(df["match_id"].nunique()),
        "current_patch_share": round(current_share, 3),
        "champion_roles": len(champions),
        "champion_roles_low_data": int(champions["low_data"].sum()),
        "matchups": len(matchups),
        "matchups_low_data": int(matchups["low_data"].sum()),
        "duos": len(duos),
        "duos_low_data": int(duos["low_data"].sum()),
        "max_abs_matchup_shift": round(float(matchups["shift"].abs().max()), 3),
        "max_abs_duo_shift": round(float(duos["shift"].abs().max()), 3),
        "profiles": int((profile["position"] == "ALL").sum()),
        "warnings": warnings,
    }


def to_markdown(summary: dict) -> str:
    lines = [f"# Aggregation report ({summary['computed_at']})", ""]
    lines += [f"- {k}: {v}" for k, v in summary.items() if k not in ("computed_at", "warnings")]
    lines += ["", "## Warnings"] + ([f"- {w}" for w in summary["warnings"]] or ["- none"])
    return "\n".join(lines) + "\n"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Rebuild aggregate tables from stored matches.")
    parser.add_argument("--db", default=Config.DATABASE_PATH)
    args = parser.parse_args(argv)
    db.init_db(args.db)
    conn = db.connect(args.db)
    summary = aggregate(conn)
    conn.close()
    text = to_markdown(summary)
    reports = Path(args.db).parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = summary["computed_at"].replace(":", "").replace("-", "")[:15]
    path = reports / f"aggregate_{stamp}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"Report saved to {path}")


if __name__ == "__main__":
    main()
