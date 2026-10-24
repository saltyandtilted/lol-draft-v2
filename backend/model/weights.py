"""Weights: AHP over three goals, and the composition of the win criterion W.

TOPSIS ranks candidates on three goals:
- W, win: A + B + C + D + lambda * S, the estimated log-odds shift of the win chance.
  A to D share one unit, so equal weights inside the block are the same as summing them.
- E, comfort (mastery and recency).
- F, team balance.

The AHP judgments compare swings over the fixed bounds in model.mcdm.BOUNDS (swing weighting):
"how much more does moving W from worst to best matter than moving E from worst to best".
Weights without that reference to the scale are meaningless; with A-D as separate criteria
full mastery outweighed a 7 percentage point strength gap, repeating the v1 mastery problem.
"""

import numpy as np

from .ahp import priorities

GOALS = ["W", "E", "F"]
# W swing (about +-12 pp of win chance) vs E swing (no mastery -> fresh full mastery)
# vs F swing (+-0.3 team quality). Resulting full-comfort value is about 3-4 pp of win chance.
#                       W    E    F
GOAL_MATRIX = np.array([
    [1.0, 7.0, 6.0],
    [1 / 7, 1.0, 1.0],
    [1 / 6, 1.0, 1.0],
])
# Risk aversion for an unknown lane opponent: expected loss = lambda * matchup spread.
BLIND_RISK = 0.5


def goal_weights(matrix=GOAL_MATRIX) -> tuple[dict, float]:
    """Weights of W, E and F (sum 1) and the AHP consistency ratio."""
    w, cr = priorities(matrix)
    return dict(zip(GOALS, (float(x) for x in w))), cr


def win_coefficients(known_enemies: int) -> dict:
    """Coefficients of A, B, C, D and S inside W for 0-5 known enemies.

    B already grows with every known enemy (it sums their matchups). Blind safety S fades out
    linearly as enemies become known.
    """
    if not 0 <= known_enemies <= 5:
        raise ValueError("known_enemies must be between 0 and 5")
    return {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "S": BLIND_RISK * (1 - known_enemies / 5)}
