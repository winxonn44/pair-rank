"""Exact ground truth. Written independently of the strategy code; tests compare the two.

Nothing here samples: every function is an exact computation.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def enumerate_binary_insertion(n: int, eps: float) -> FloatArray:
    """Exact P[r, s]: probability binary insertion ends in slot s when the true slot is r.

    Model: M-const (each answer wrong with probability eps, independently) and the
    midpoint rule mid = (lo + hi) // 2 over the slot interval [lo, hi]. Enumerates
    every branch of the search, so at most 2**ceil(log2(n + 1)) leaves per true slot.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if not 0.0 <= eps <= 1.0:
        raise ValueError(f"eps must be in [0, 1], got {eps}")
    p = np.zeros((n + 1, n + 1), dtype=np.float64)

    def walk(r: int, lo: int, hi: int, prob: float) -> None:
        if lo >= hi:
            p[r, lo] += prob
            return
        mid = (lo + hi) // 2
        correct_is_better = r <= mid
        # the branch the correct answer takes, then the wrong one
        for says_better, q in ((correct_is_better, 1.0 - eps), (not correct_is_better, eps)):
            if q == 0.0:
                continue
            if says_better:
                walk(r, lo, mid, prob * q)
            else:
                walk(r, mid + 1, hi, prob * q)

    for r in range(n + 1):
        walk(r, 0, n, 1.0)
    return p


def mean_abs_error(p: FloatArray) -> float:
    """E|s - r| with the true slot r uniform on {0, ..., n}."""
    n_slots = p.shape[0]
    idx = np.arange(n_slots)
    dist = np.abs(idx[None, :] - idx[:, None])
    return float(np.sum(p * dist) / n_slots)


def signed_error_pmf(p: FloatArray) -> dict[int, float]:
    """P(s - r = e) with r uniform, for every e with nonzero probability."""
    n_slots = p.shape[0]
    pmf: dict[int, float] = {}
    rs, ss = np.nonzero(p)
    for r, s in zip(rs.tolist(), ss.tolist(), strict=True):
        e = s - r
        pmf[e] = pmf.get(e, 0.0) + float(p[r, s]) / n_slots
    return dict(sorted(pmf.items()))


def exact_slot_posterior(answers: Sequence[tuple[int, bool]], n: int, eps: float) -> FloatArray:
    """Posterior over the n + 1 slots after `answers`, by brute-force Bayes.

    Uniform prior; M-const likelihood: an answer (j, better) has probability
    1 - eps if it is correct for slot r (better <=> r <= j), else eps.
    """
    slots = np.arange(n + 1)
    log_post = np.zeros(n + 1, dtype=np.float64)
    log_right, log_wrong = np.log1p(-eps), np.log(eps) if eps > 0 else -np.inf
    for j, better in answers:
        if not 0 <= j < n:
            raise ValueError(f"position {j} is outside a list of {n}")
        correct = (slots <= j) == better
        log_post += np.where(correct, log_right, log_wrong)
    log_post -= np.max(log_post)
    post = np.exp(log_post)
    return np.asarray(post / post.sum(), dtype=np.float64)


def kendall_tau_bruteforce(x: Sequence[float], y: Sequence[float]) -> float:
    """Kendall's tau-a by checking all pairs, O(N^2). The test oracle for faster versions."""
    m = len(x)
    if m != len(y) or m < 2:
        raise ValueError("need two sequences of the same length >= 2")
    score = 0
    for i in range(m):
        for j in range(i + 1, m):
            a = (x[i] > x[j]) - (x[i] < x[j])
            b = (y[i] > y[j]) - (y[i] < y[j])
            score += a * b
    return score / (m * (m - 1) / 2)
