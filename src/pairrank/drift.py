"""Score histories: every entry's 0-10 score after every insertion (Q2)."""

from __future__ import annotations

from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

from pairrank.conventions import DISPLAY_DECIMALS, Tier
from pairrank.scoring import percentile_scores, tier_scores
from pairrank.sim.noise import NoiseModel
from pairrank.sim.session import run_insertion
from pairrank.strategies.base import Strategy

FloatArray = NDArray[np.float64]
Mapping = Literal["percentile", "tiered"]

# Equal-probability tiers for N(0, 1) utilities.
_LOWER = float(norm.ppf(1.0 / 3.0))
_UPPER = float(norm.ppf(2.0 / 3.0))


def true_tier(utility: float) -> Tier:
    """The tier a user picks. Assumed correct: comparisons are the noisy part."""
    if utility < _LOWER:
        return "disliked"
    return "fine" if utility < _UPPER else "liked"


def true_scores(utilities: FloatArray) -> FloatArray:
    """The score each place 'really' deserves: 10 x its true quantile."""
    return np.asarray(10.0 * norm.cdf(utilities), dtype=np.float64)


def score_history(
    strategy: Strategy,
    utilities: FloatArray,
    noise: NoiseModel,
    rng: np.random.Generator,
    mapping: Mapping,
) -> FloatArray:
    """S[t, i]: place i's score once t + 1 places are ranked; NaN before it arrives.

    Places arrive in index order. Under the tiered mapping each place goes straight
    to its true tier and is compared only within that tier.
    """
    n_places = utilities.shape[0]
    user_noise = noise.fresh()
    groups: dict[str, list[int]] = {}
    history = np.full((n_places, n_places), np.nan, dtype=np.float64)
    for new_id in range(n_places):
        key = true_tier(float(utilities[new_id])) if mapping == "tiered" else "all"
        members = groups.setdefault(key, [])
        ids = np.asarray(members, dtype=np.int64)
        result = run_insertion(
            strategy,
            utilities[ids],
            float(utilities[new_id]),
            user_noise,
            rng,
            list_ids=ids,
            new_id=new_id,
        )
        members.insert(result.slot, new_id)
        for name, group in groups.items():
            scores = (
                percentile_scores(len(group))
                if mapping == "percentile"
                else tier_scores(_as_tier(name), len(group))
            )
            history[new_id, group] = scores
    return history


def _as_tier(name: str) -> Tier:
    if name in ("disliked", "fine", "liked"):
        return cast(Tier, name)
    raise ValueError(f"not a tier: {name!r}")


def mean_abs_drift(history: FloatArray, a: int, b: int) -> float:
    """Mean |score at time b - score at time a|, over places already ranked at time a."""
    return float(np.mean(np.abs(history[b, : a + 1] - history[a, : a + 1])))


def visible_churn(history: FloatArray, t: int) -> float:
    """Fraction of earlier entries whose displayed score changes when place t is added."""
    before = np.round(history[t - 1, :t], DISPLAY_DECIMALS)
    after = np.round(history[t, :t], DISPLAY_DECIMALS)
    return float(np.mean(before != after))


def expected_churn(n: int) -> float:
    """Predicted visible churn when inserting into a list of n, for a uniform slot.

    A change of |delta| flips a one-decimal display with probability min(1, |delta| / 0.1)
    if the score's position within its rounding bin is uniform.
    """
    positions = np.arange(n, dtype=np.float64)
    total = 0.0
    for slot in range(n + 1):
        delta = np.where(positions < slot, positions, n - 1 - positions) * 10.0 / (n * (n - 1))
        total += float(np.mean(np.minimum(1.0, np.abs(delta) / 0.1)))
    return total / (n + 1)
