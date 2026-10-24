"""The original v1 model as a comparison function only.

Re-implemented from the v1 Flask endpoint, including its known flaws, so that v2 can be compared
against what v1 actually did: L2 normalization with ideals from the current offer, one role per
champion, Counter counted from WeakAgainst as a benefit, and Balance identical for every candidate
(v1 looked allies up among the candidates, so the AD count was always 0).
v1 data (champions.json) is read from the v1 folder and never copied into this repository.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

V1_CHAMPIONS = Path(r"C:\projekty\lol-draft\backend\champions.json")
V1_WEIGHTS = {"Popularity": 0.032, "Winrate": 0.119, "Mastery": 0.391,
              "Synergy": 0.086, "Counter": 0.285, "Balance": 0.088}
V1_ROLE = {"TOP": "Top", "JUNGLE": "Jungler", "MIDDLE": "Mid", "BOTTOM": "AD Carry", "UTILITY": "Support"}


def load_v1_champions(path: Path = V1_CHAMPIONS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["champions"]


def v1_rank(champions: list[dict], position: str, ally_ids: list[int], enemy_ids: list[int],
            ban_ids: list[int], mastery: dict[int, int] | None = None, top_n: int = 5) -> list[int]:
    """Champion ids in v1 order. Inputs are champion ids; v1 itself worked with names."""
    mastery = mastery or {}
    by_id = {c["ChampionId"]: c["Name"] for c in champions}
    team_picks = [by_id[i] for i in ally_ids if i in by_id]
    enemy_picks = [by_id[i] for i in enemy_ids if i in by_id]
    taken = set(team_picks + enemy_picks + [by_id[i] for i in ban_ids if i in by_id])

    pool = [c for c in champions if c.get("Position") == V1_ROLE[position] and c["Name"] not in taken]
    if not pool:
        return []
    df = pd.DataFrame(pool)
    df["Popularity"] = pd.to_numeric(df["Popularity"], errors="coerce").fillna(0)
    df["Winrate"] = pd.to_numeric(df["Winrate"], errors="coerce").fillna(0)
    df["Mastery"] = np.log1p(df["ChampionId"].map(mastery).fillna(0))
    df["Synergy"] = df["GoodWith"].apply(lambda x: len(set(x or []) & set(team_picks)))
    df["Counter"] = df["WeakAgainst"].apply(lambda x: len(set(x or []) & set(enemy_picks)))
    ad_count = sum(1 for name in team_picks
                   if not df[df["Name"] == name].empty and df[df["Name"] == name].iloc[0]["DamageType"] == "AD")
    df["Balance"] = -abs(ad_count - (len(team_picks) - ad_count) - 1)

    criteria = list(V1_WEIGHTS)
    norm = df[criteria] / np.sqrt((df[criteria] ** 2).sum())
    norm = norm.fillna(0)  # v1 divided by zero for all-zero columns; treat as 0
    weighted = norm * np.array([V1_WEIGHTS[c] for c in criteria])
    best, worst = weighted.max(), weighted.min()
    d_best = np.sqrt(((weighted - best) ** 2).sum(axis=1))
    d_worst = np.sqrt(((weighted - worst) ** 2).sum(axis=1))
    df["score"] = d_worst / (d_best + d_worst + 1e-9)
    return df.sort_values("score", ascending=False)["ChampionId"].head(top_n).astype(int).tolist()
