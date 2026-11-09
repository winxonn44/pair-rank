"""Turning positions into 0-10 scores (Q2). Conventions are in docs/conventions.md.

Scores are never stored: they are a pure function of position and list size.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from pairrank.conventions import SCORE_MAX, TIER_BANDS, Tier

FloatArray = NDArray[np.float64]


def percentile_scores(n: int) -> FloatArray:
    """Score of each position in a list of n: 10 for the best, 0 for the worst."""
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if n == 1:
        return np.array([SCORE_MAX], dtype=np.float64)
    return np.asarray(SCORE_MAX * (n - 1 - np.arange(n)) / max(n - 1, 1), dtype=np.float64)


def percentile_delta(n: int, slot: int) -> FloatArray:
    """Exact change in each old entry's score when a place is inserted at `slot` (n >= 2)."""
    if n < 2 or not 0 <= slot <= n:
        raise ValueError(f"need n >= 2 and 0 <= slot <= n, got n={n}, slot={slot}")
    positions = np.arange(n)
    above = SCORE_MAX * positions / (n * (n - 1))
    below = -SCORE_MAX * (n - 1 - positions) / (n * (n - 1))
    return np.asarray(np.where(positions < slot, above, below), dtype=np.float64)


def tier_scores(tier: Tier, m: int) -> FloatArray:
    """Score of each position within one tier of m entries, using mid-ranks.

    Mid-ranks keep the top of one tier from colliding with the bottom of the next,
    and a lone entry sits mid-band.
    """
    if m < 0:
        raise ValueError(f"m must be >= 0, got {m}")
    lo, hi = TIER_BANDS[tier]
    return np.asarray(lo + (hi - lo) * (m - np.arange(m) - 0.5) / max(m, 1), dtype=np.float64)
