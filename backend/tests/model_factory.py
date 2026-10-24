"""TEST DATA ONLY: small synthetic aggregates for model tests. Not real champion statistics."""

import pandas as pd

from model.data import Aggregates

# Champion ids 1-6 are TOP candidates, 50-54 are allies/enemies in other roles.
AD_TANK, AD_CARRY, AP_MAGE, AP_TANK, WEAK, FLEX = 1, 2, 3, 4, 5, 6


def champion_rows():
    rows = [
        # champion, position, games, dev_logodds, role_share, matchup_spread
        (AD_TANK, "TOP", 400, 0.10, 0.95, 0.05),
        (AD_CARRY, "TOP", 300, 0.05, 0.90, 0.20),
        (AP_MAGE, "TOP", 200, 0.00, 0.60, 0.10),
        (AP_TANK, "TOP", 250, 0.02, 0.97, 0.02),
        (WEAK, "TOP", 150, -0.20, 0.99, 0.08),
        (FLEX, "TOP", 10, 0.01, 0.03, 0.00),  # below 5 % role share: not a TOP candidate
        (FLEX, "MIDDLE", 300, 0.04, 0.97, 0.05),
    ]
    rows += [(50 + i, pos, 300, 0.0, 1.0, 0.05)
             for i, pos in enumerate(["JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", "TOP"])]
    frame = pd.DataFrame(rows, columns=["champion_id", "position", "games", "dev_logodds",
                                        "role_share", "matchup_spread"])
    frame["w_games"] = frame["games"]
    frame["posterior_mean"] = 0.5 + frame["dev_logodds"] / 4  # linear approximation of sigmoid
    frame["ci_low"] = frame["posterior_mean"] - 0.03
    frame["ci_high"] = frame["posterior_mean"] + 0.03
    frame["low_data"] = frame["games"] < 20
    return frame


def profile_rows():
    # champion, position, games, physical_share, damage_per_min, tanked_per_min, cc_per_min
    rows = [
        (AD_TANK, "TOP", 400, 0.9, 500, 2000, 1.0),
        (AD_CARRY, "TOP", 300, 0.9, 900, 800, 0.2),
        (AP_MAGE, "TOP", 200, 0.1, 900, 700, 0.6),
        (AP_TANK, "TOP", 250, 0.15, 500, 2100, 1.2),
        (WEAK, "TOP", 150, 0.8, 600, 1200, 0.5),
        (FLEX, "MIDDLE", 300, 0.2, 800, 900, 0.5),
        (50, "JUNGLE", 300, 0.9, 600, 1500, 0.8),
        (51, "MIDDLE", 300, 0.9, 800, 800, 0.4),
        (52, "BOTTOM", 300, 0.95, 900, 700, 0.2),
        (53, "UTILITY", 300, 0.9, 400, 900, 0.9),
        (54, "TOP", 300, 0.8, 600, 1500, 0.6),
    ]
    frame = pd.DataFrame(rows, columns=["champion_id", "position", "games", "physical_share",
                                        "damage_per_min", "tanked_per_min", "cc_per_min"])
    overall = frame.assign(position="ALL")
    return pd.concat([frame, overall], ignore_index=True)


def make_aggregates(matchups=(), duos=()) -> Aggregates:
    """`matchups`: (champion, position, enemy, lane, shift, games); `duos`: (champion, position, ally, shift, games)."""
    m = pd.DataFrame(list(matchups), columns=["champion_id", "position", "enemy_champion_id", "lane",
                                              "shift", "games"])
    d = pd.DataFrame(list(duos), columns=["champion_id", "position", "ally_champion_id", "shift", "games"])
    return Aggregates(champion_rows(), m, d, profile_rows(),
                      {"current_patch": "TEST", "computed_at": "TEST", "matches_used": 0})
