"""Top 5 recommendation for a draft: ranking, score breakdown, uncertainty and robustness checks."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import criteria, mcdm, smaa
from .data import Aggregates, Draft, PlayerProfile
from .weights import goal_weights, win_coefficients

TOP_N = 5
MIN_PAIR_GAMES = 30

# Short English reasons for the UI: (positive, negative).
REASONS = {
    "A": ("strong in this role on the current patch", "weak in this role on the current patch"),
    "B": ("favourable matchups against known enemies", "countered by known enemies"),
    "C": ("good synergy with your allies", "poor synergy with your allies"),
    "D": ("you win more than average on this champion", "you win less than average on this champion"),
    "S": ("safe blind pick (few bad matchups)", "matchup dependent"),
    "E": ("comfortable champion for you (mastery)", "little experience on this champion"),
    "F": ("improves your team's damage mix, frontline or CC", "makes your team composition worse"),
}
# A reason is shown only if its effect equals at least this shift of W (about 0.5 pp).
MIN_REASON_LOGODDS = 0.02
CLOSE_CALL = "close call: no single criterion stands out"
# Raw values that count as "neutral" when explaining a candidate. S is compared with the
# median candidate instead ("safer than the others"), set per draft in recommend().
NEUTRAL = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0, "S": None, "E": 0.3, "F": 0.0}


@dataclass
class Recommendation:
    candidates: list[dict]
    meta: dict


def percentage_points(logodds: float) -> float:
    return round(float((1 / (1 + np.exp(-logodds)) - 0.5) * 100), 2)


def _effect_size(c: str, value: float, neutral: dict, goals: dict, coef: dict) -> float:
    """Effect of one criterion on the TOPSIS scale: goal weight times the share of the goal's range."""
    goal = "W" if c in coef else c
    low, high = mcdm.BOUNDS[goal]
    return goals[goal] * coef.get(c, 1.0) * (value - neutral[c]) / (high - low)


def _why(row: pd.Series, neutral: dict, goals: dict, coef: dict, active: list[str]) -> list[str]:
    effects = {}
    for c in ["A", "B", "C", "D", "S", "E", "F"]:
        goal = "W" if c in coef else c
        if goal in active and coef.get(c, 1.0) > 0:
            effects[c] = _effect_size(c, row[c], neutral, goals, coef)
    low, high = mcdm.BOUNDS["W"]
    threshold = goals["W"] * MIN_REASON_LOGODDS / (high - low)
    ordered = sorted(effects.items(), key=lambda kv: kv[1], reverse=True)
    reasons = [REASONS[c][0] for c, e in ordered[:2] if e >= threshold]
    worst_c, worst_e = ordered[-1]
    if worst_e <= -threshold:
        reasons.append(REASONS[worst_c][1])
    return reasons or [CLOSE_CALL]


def recommend(agg: Aggregates, draft: Draft, profile: PlayerProfile | None = None,
              top_n: int = TOP_N, smaa_samples: int = smaa.SAMPLES,
              stability_k: int | None = None) -> Recommendation:
    """`stability_k` is the k of "probability to stay in the top k" (default: top_n)."""
    values = criteria.compute(agg, draft, profile)
    weights, cr = goal_weights()
    coef = win_coefficients(draft.known_enemies)
    meta = {
        "patch": agg.meta.get("current_patch"),
        "data_computed_at": agg.meta.get("computed_at"),
        "matches_used": agg.meta.get("matches_used"),
        "position": draft.position,
        "known_enemies": draft.known_enemies,
        "candidates": len(values),
        "ahp_cr": round(cr, 4),
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "win_coefficients": coef,
    }
    if values.empty:
        return Recommendation([], {**meta, "dropped_criteria": [], "spearman": {}})

    norm = mcdm.normalize(values[criteria.GOALS])
    active, dropped = mcdm.active_criteria(norm, weights)
    if not active:
        # Every goal is constant: keep W so the order is still defined.
        active = ["W"]
    score = mcdm.topsis(norm, weights, active)
    promethee = mcdm.promethee_ii(norm, weights, active)
    vikor = mcdm.vikor(norm, weights, active)
    stability = smaa.top_k_probability(norm, weights, active, samples=smaa_samples,
                                         k=stability_k or top_n)
    meta["dropped_criteria"] = dropped
    meta["spearman"] = {
        "promethee_ii": round(mcdm.spearman(score, promethee), 3),
        "vikor": round(mcdm.spearman(score, -vikor), 3),
    }

    neutral = {**NEUTRAL, "S": float(values["S"].median())}
    win_logodds = values[["A", "B", "C", "D"]].sum(axis=1)
    order = score.sort_values(ascending=False).index[:top_n]
    w_active = {c: weights[c] for c in active}
    total_w = sum(w_active.values())
    results = []
    for rank, champion_id in enumerate(order, start=1):
        row = values.loc[champion_id]
        results.append({
            "rank": rank,
            "champion_id": int(champion_id),
            "name": agg.names.get(int(champion_id), str(champion_id)),
            "score": round(float(score[champion_id]), 4),
            "win_estimate": round(float(1 / (1 + np.exp(-win_logodds[champion_id]))), 4),
            "criteria": {c: round(float(row[c]), 4) for c in criteria.GOALS + criteria.CRITERIA},
            "criteria_pp": {c: percentage_points(row[c]) for c in ["A", "B", "C", "D"]},
            # Share of the weighted normalized value per active criterion.
            "contributions": {c: round(float(w_active[c] / total_w * norm.loc[champion_id, c]), 4)
                              for c in active},
            "why": _why(row, neutral, weights, coef, active),
            "games": int(row["games"]),
            "interval_pp": round(float((row["ci_high"] - row["ci_low"]) * 100), 1),
            "low_data": {
                "A": bool(row["low_data"]),
                "B": bool(draft.enemies) and int(row["games_B"]) < MIN_PAIR_GAMES,
                "C": bool(draft.allies) and int(row["games_C"]) < MIN_PAIR_GAMES,
            },
            "top5_probability": round(float(stability[champion_id]), 3),
            "promethee_rank": int(promethee.rank(ascending=False)[champion_id]),
            "vikor_rank": int(vikor.rank(ascending=True)[champion_id]),
        })
    return Recommendation(results, meta)
