"""L2-regularised logistic regression (Newton's method), used only as a diagnostic.

It checks whether the summed criteria A-C explain match outcomes and how strongly. The weights
of A-D stay equal until milestone 6, when there is enough data to trust the coefficients.
The diagnostic is in-sample (aggregates come from the same matches), so it is optimistic.
"""

import numpy as np
import pandas as pd


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, iterations: int = 50) -> np.ndarray:
    """Coefficients [intercept, b1, ...]; the intercept is not penalised."""
    x = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(x.shape[1])
    penalty = np.full(x.shape[1], l2)
    penalty[0] = 0.0
    for _ in range(iterations):
        p = 1 / (1 + np.exp(-x @ beta))
        gradient = x.T @ (y - p) - penalty * beta
        hessian = x.T @ (x * (p * (1 - p))[:, None]) + np.diag(penalty)
        step = np.linalg.solve(hessian, gradient)
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def load_parts(conn) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT p.match_id, p.team_id, p.position, p.champion_id, m.blue_win, m.patch "
        "FROM participants p JOIN matches m ON m.match_id = p.match_id",
        conn,
    )


def match_features(parts: pd.DataFrame, champions: pd.DataFrame, matchups: pd.DataFrame,
                   duos: pd.DataFrame) -> pd.DataFrame:
    """Per match: blue minus red sums of A, lane B and C, plus blue_win. `parts` from load_parts."""
    parts = parts[["match_id", "team_id", "position", "champion_id", "blue_win"]].copy()
    a = champions.set_index(["champion_id", "position"])["dev_logodds"]
    parts["A"] = a.reindex(pd.MultiIndex.from_frame(parts[["champion_id", "position"]])).fillna(0).to_numpy()

    enemy = parts.merge(parts, on=["match_id", "position"], suffixes=("", "_o"))
    enemy = enemy[enemy["team_id"] != enemy["team_id_o"]]
    lane = matchups[matchups["lane"] == 1].set_index(["champion_id", "position", "enemy_champion_id"])["shift"]
    enemy["B"] = lane.reindex(pd.MultiIndex.from_frame(
        enemy[["champion_id", "position", "champion_id_o"]])).fillna(0).to_numpy()

    ally = parts.merge(parts, on=["match_id", "team_id"], suffixes=("", "_o"))
    ally = ally[ally["position"] != ally["position_o"]]
    duo = duos.set_index(["champion_id", "position", "ally_champion_id"])["shift"]
    # Each pair appears twice (both orientations); halve to count it once.
    ally["C"] = duo.reindex(pd.MultiIndex.from_frame(
        ally[["champion_id", "position", "champion_id_o"]])).fillna(0).to_numpy() / 2

    per_team = pd.concat([
        parts.groupby(["match_id", "team_id"])["A"].sum(),
        enemy.groupby(["match_id", "team_id"])["B"].sum(),
        ally.groupby(["match_id", "team_id"])["C"].sum(),
    ], axis=1).fillna(0).reset_index()
    blue = per_team[per_team["team_id"] == 100].set_index("match_id")
    red = per_team[per_team["team_id"] == 200].set_index("match_id")
    diff = (blue[["A", "B", "C"]] - red[["A", "B", "C"]]).dropna()
    diff["blue_win"] = parts.groupby("match_id")["blue_win"].first().reindex(diff.index)
    return diff


def diagnostic(conn, champions, matchups, duos, l2: float = 1.0) -> dict:
    features = match_features(load_parts(conn), champions, matchups, duos)
    beta = fit_logistic(features[["A", "B", "C"]].to_numpy(), features["blue_win"].to_numpy(), l2)
    return {
        "matches": len(features),
        "intercept": round(float(beta[0]), 3),
        "coef_A": round(float(beta[1]), 3),
        "coef_B": round(float(beta[2]), 3),
        "coef_C": round(float(beta[3]), 3),
    }
