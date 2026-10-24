"""Weight uncertainty by Monte Carlo (SMAA style): how often a candidate stays in the top 5."""

import numpy as np
import pandas as pd

from .mcdm import _weight_vector, topsis_batch

SAMPLES = 1000
# Dirichlet concentration: higher means samples stay closer to the AHP weights.
CONCENTRATION = 50
TOP_K = 5


def top_k_probability(norm: pd.DataFrame, weights: dict, active: list[str],
                      samples: int = SAMPLES, concentration: float = CONCENTRATION,
                      k: int = TOP_K, seed: int = 0) -> pd.Series:
    w = _weight_vector(weights, active)
    rng = np.random.default_rng(seed)
    sampled = rng.dirichlet(concentration * w, size=samples)
    scores = topsis_batch(norm[active].to_numpy(), sampled)
    k = min(k, len(norm))
    top = np.argsort(-scores, axis=1)[:, :k]
    counts = np.bincount(top.ravel(), minlength=len(norm))
    return pd.Series(counts / samples, index=norm.index)
