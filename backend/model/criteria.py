"""Criteria A to F (plus blind safety S) for every candidate in a draft.

A to D and S are log-odds shifts of the win chance, so A + B + C + D estimates the change
of the win chance. E (comfort) and F (team balance) carry preferences.
"""

import numpy as np
import pandas as pd

from .data import Aggregates, Draft, PlayerProfile
from .weights import win_coefficients

MIN_ROLE_SHARE = 0.05
# Matchups against enemies outside the lane are estimated from coarser data: count them half.
OFF_LANE_WEIGHT = 0.5
# Personal form: half-life of a game's weight and prior strength in games.
FORM_HALF_LIFE_DAYS = 30
FORM_PRIOR_GAMES = 10
# Comfort: mastery saturates at this many points; recency decays with this time constant.
MASTERY_SATURATION = 200_000
RECENCY_DAYS = 90
# Team balance: profiles with fewer games fall back to the champion's all-role profile.
MIN_PROFILE_GAMES = 5
PHYSICAL_SHARE_TOLERANCE = 0.3

CRITERIA = ["A", "B", "C", "D", "S", "E", "F"]
# Goals ranked by TOPSIS: W combines A-D and S (see model.weights).
GOALS = ["W", "E", "F"]


def logit(p):
    return np.log(p / (1 - p))


def candidates(agg: Aggregates, draft: Draft) -> pd.DataFrame:
    """Champions viable in the role (role share >= 5 %) that are not banned or picked."""
    pool = agg.champions[
        (agg.champions["position"] == draft.position) & (agg.champions["role_share"] >= MIN_ROLE_SHARE)
    ]
    pool = pool[~pool["champion_id"].isin(draft.unavailable)]
    return pool.set_index("champion_id")


def counter(agg: Aggregates, draft: Draft, ids: pd.Index) -> tuple[pd.Series, pd.Series]:
    """B: sum of matchup shifts against known enemies. Returns (B, games behind B)."""
    b = pd.Series(0.0, index=ids)
    games = pd.Series(0, index=ids)
    m = agg.matchups[(agg.matchups["position"] == draft.position) & agg.matchups["champion_id"].isin(ids)]
    for enemy in draft.enemies:
        lane = int(enemy.position == draft.position)
        rows = m[(m["enemy_champion_id"] == enemy.champion_id) & (m["lane"] == lane)]
        rows = rows.set_index("champion_id")
        weight = 1.0 if lane else OFF_LANE_WEIGHT
        b = b.add(weight * rows["shift"], fill_value=0.0).reindex(ids)
        games = games.add(rows["games"], fill_value=0).reindex(ids)
    return b.astype(float), games.astype(int)


def synergy(agg: Aggregates, draft: Draft, ids: pd.Index) -> tuple[pd.Series, pd.Series]:
    """C: sum of duo shifts with known allies. Returns (C, games behind C)."""
    c = pd.Series(0.0, index=ids)
    games = pd.Series(0, index=ids)
    d = agg.duos[(agg.duos["position"] == draft.position) & agg.duos["champion_id"].isin(ids)]
    for ally in draft.allies:
        rows = d[d["ally_champion_id"] == ally.champion_id].set_index("champion_id")
        c = c.add(rows["shift"], fill_value=0.0).reindex(ids)
        games = games.add(rows["games"], fill_value=0).reindex(ids)
    return c.astype(float), games.astype(int)


def personal_form(profile: PlayerProfile, global_rate: pd.Series) -> pd.Series:
    """D: the player's decayed win rate on a champion versus the champion's global rate.

    Smoothed towards the global rate with FORM_PRIOR_GAMES; an unplayed champion gets 0.
    """
    d = pd.Series(0.0, index=global_rate.index)
    for champion_id in global_rate.index:
        games = [g for g in profile.games if g.champion_id == champion_id]
        if not games:
            continue
        w = np.array([0.5 ** (g.days_ago / FORM_HALF_LIFE_DAYS) for g in games])
        wins = np.array([g.win for g in games], dtype=float)
        p_global = global_rate[champion_id]
        personal = (w @ wins + FORM_PRIOR_GAMES * p_global) / (w.sum() + FORM_PRIOR_GAMES)
        d[champion_id] = logit(personal) - logit(p_global)
    return d


def comfort(profile: PlayerProfile, ids: pd.Index) -> pd.Series:
    """E: saturated log mastery times recency, in [0, 1]."""
    values = {}
    for champion_id in ids:
        m = profile.mastery.get(champion_id)
        if m is None:
            values[champion_id] = 0.0
            continue
        level = min(1.0, np.log1p(m.points) / np.log1p(MASTERY_SATURATION))
        recency = 0.5 + 0.5 * np.exp(-m.days_since_played / RECENCY_DAYS)
        values[champion_id] = level * recency
    return pd.Series(values, index=ids, dtype=float)


# --- F: team balance ----------------------------------------------------------------------------


def _profile_lookup(agg: Aggregates):
    p = agg.profile.set_index(["champion_id", "position"])
    by_role = agg.profile[agg.profile["position"] != "ALL"]
    role_avg = {}
    for position, g in by_role.groupby("position"):
        w = g["games"]
        role_avg[position] = {
            col: float(np.average(g[col], weights=w))
            for col in ("physical_share", "damage_per_min", "tanked_per_min", "cc_per_min")
        }

    def lookup(champion_id: int, position: str) -> dict:
        for key in ((champion_id, position), (champion_id, "ALL")):
            if key in p.index and p.loc[key, "games"] >= MIN_PROFILE_GAMES:
                return p.loc[key, ["physical_share", "damage_per_min", "tanked_per_min", "cc_per_min"]].to_dict()
        return role_avg[position]  # no data: assume a typical champion of the role

    return lookup, role_avg


def team_quality(members: list[dict], targets: dict) -> float:
    """Q in [0, 1]: damage mix near the typical team, enough frontline and CC.

    `members` are champion profiles; `targets` are sums of role averages for the same positions.
    """
    if not members:
        return 1 / 3  # no damage mix to judge, frontline and CC fully missing
    damage = sum(m["damage_per_min"] for m in members)
    physical = sum(m["physical_share"] * m["damage_per_min"] for m in members) / damage
    mix_error = min(1.0, abs(physical - targets["physical_share"]) / PHYSICAL_SHARE_TOLERANCE)
    tank_short = max(0.0, 1 - sum(m["tanked_per_min"] for m in members) / targets["tanked_per_min"])
    cc_short = max(0.0, 1 - sum(m["cc_per_min"] for m in members) / targets["cc_per_min"])
    return 1 - (mix_error + tank_short + cc_short) / 3


def _targets(role_avg: dict, positions: list[str]) -> dict:
    damage = sum(role_avg[p]["damage_per_min"] for p in positions)
    return {
        "physical_share": sum(role_avg[p]["physical_share"] * role_avg[p]["damage_per_min"] for p in positions)
        / damage,
        "tanked_per_min": sum(role_avg[p]["tanked_per_min"] for p in positions),
        "cc_per_min": sum(role_avg[p]["cc_per_min"] for p in positions),
    }


def balance(agg: Aggregates, draft: Draft, ids: pd.Index) -> pd.Series:
    """F = (Q(team + candidate) - Q(team)) * allies / 4, so it depends on the candidate.

    Balance only means something once the team takes shape: with no allies F is 0 for everybody
    (and drops out of TOPSIS), and its effect grows with every known ally.
    """
    if not draft.allies:
        return pd.Series(0.0, index=ids)
    scale = len(draft.allies) / 4
    lookup, role_avg = _profile_lookup(agg)
    team = [lookup(a.champion_id, a.position) for a in draft.allies]
    positions = [a.position for a in draft.allies]
    before = team_quality(team, _targets(role_avg, positions))
    after_targets = _targets(role_avg, positions + [draft.position])
    return pd.Series(
        [scale * (team_quality(team + [lookup(c, draft.position)], after_targets) - before) for c in ids],
        index=ids,
        dtype=float,
    )


# --- All criteria -------------------------------------------------------------------------------


def compute(agg: Aggregates, draft: Draft, profile: PlayerProfile | None = None) -> pd.DataFrame:
    """One row per candidate: criteria A-F, S and the evidence behind them."""
    profile = profile or PlayerProfile()
    pool = candidates(agg, draft)
    if pool.empty:
        return pd.DataFrame(columns=GOALS + CRITERIA)
    ids = pool.index
    b, b_games = counter(agg, draft, ids)
    c, c_games = synergy(agg, draft, ids)
    out = pd.DataFrame(
        {
            "A": pool["dev_logodds"],
            "B": b,
            "C": c,
            "D": personal_form(profile, pool["posterior_mean"]),
            "S": -pool["matchup_spread"],
            "E": comfort(profile, ids),
            "F": balance(agg, draft, ids),
            "games": pool["games"],
            "ci_low": pool["ci_low"],
            "ci_high": pool["ci_high"],
            "posterior_mean": pool["posterior_mean"],
            "low_data": pool["low_data"].astype(bool),
            "games_B": b_games,
            "games_C": c_games,
        },
        index=ids,
    )
    coef = win_coefficients(draft.known_enemies)
    out.insert(0, "W", sum(coef[c] * out[c] for c in coef))
    if out[CRITERIA + GOALS].isna().any().any():
        raise ValueError("criteria contain missing values")
    return out
