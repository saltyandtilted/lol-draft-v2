"""Analytic Hierarchy Process with mandatory reciprocity and consistency checks.

v1 used a non-reciprocal Saaty matrix without a consistency check; here both are enforced.
"""

import numpy as np

# Saaty's random consistency index by matrix size.
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
MAX_CR = 0.1


class AhpError(ValueError):
    pass


def check_reciprocal(matrix: np.ndarray, tol: float = 1e-6) -> None:
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise AhpError("AHP matrix must be square")
    if (matrix <= 0).any():
        raise AhpError("AHP matrix must be positive")
    if not np.allclose(np.diag(matrix), 1, atol=tol):
        raise AhpError("AHP matrix must have ones on the diagonal")
    if not np.allclose(matrix * matrix.T, 1, atol=tol):
        bad = np.argwhere(~np.isclose(matrix * matrix.T, 1, atol=tol))[0]
        raise AhpError(f"AHP matrix is not reciprocal at {tuple(bad)}: a_ij * a_ji must be 1")


def priorities(matrix) -> tuple[np.ndarray, float]:
    """Principal eigenvector weights and the consistency ratio. Raises AhpError if CR >= 0.1."""
    matrix = np.asarray(matrix, dtype=float)
    check_reciprocal(matrix)
    n = matrix.shape[0]
    eigenvalues, eigenvectors = np.linalg.eig(matrix)
    k = int(np.argmax(eigenvalues.real))
    weights = np.abs(eigenvectors[:, k].real)
    weights /= weights.sum()
    lambda_max = eigenvalues[k].real
    ci = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    cr = ci / RANDOM_INDEX[n] if RANDOM_INDEX.get(n) else 0.0
    if cr >= MAX_CR:
        raise AhpError(f"AHP matrix is inconsistent: CR = {cr:.3f} >= {MAX_CR}")
    return weights, float(cr)
