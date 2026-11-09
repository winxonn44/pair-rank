"""S3a: probabilistic bisection. Keep a posterior over the n + 1 slots; ask at its median.

The likelihood assumes each answer is wrong with probability eps_hat. Stops when the
most likely slot has probability >= 1 - delta, or after a question budget.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from pairrank.conventions import DEFAULT_EPS
from pairrank.state import Answer, InsertionState
from pairrank.strategies.base import Placed, Query, Step, Strategy

DEFAULT_DELTA = 0.1
BUDGET_MULTIPLIER = 4


def slot_posterior(n: int, answers: Sequence[Answer], eps_hat: float) -> NDArray[np.float64]:
    """Posterior over slots, updated one answer at a time (tested against the oracle)."""
    post = np.full(n + 1, 1.0 / (n + 1), dtype=np.float64)
    for j, new_is_better in answers:
        # An answer "better than position j" is correct for slots 0..j, wrong for the rest.
        cut = j + 1
        right, wrong = 1.0 - eps_hat, eps_hat
        if new_is_better:
            post[:cut] *= right
            post[cut:] *= wrong
        else:
            post[:cut] *= wrong
            post[cut:] *= right
        post /= post.sum()
    return post


def posterior_median_position(post: NDArray[np.float64]) -> int:
    """The question position whose yes/no split of the posterior is closest to 50/50.

    Not simply "first j with P(slot <= j) >= 1/2": on a posterior like [.47, .47, .06]
    that rule keeps asking j = 1 and can never separate slots 0 and 1 (found by the
    noise-free exactness test; see docs/RESULTS.md).
    """
    n = post.shape[0] - 1
    return int(np.argmin(np.abs(np.cumsum(post)[:n] - 0.5)))


def question_budget(n: int) -> int:
    return BUDGET_MULTIPLIER * math.ceil(math.log2(n + 1)) if n > 0 else 0


def bisection_step(
    n: int, answers: Sequence[Answer], eps_hat: float, delta: float, budget: int
) -> Step:
    """One step of bisection from any transcript (S4 reuses this after a contradiction)."""
    if n == 0:
        return Placed(0)
    post = slot_posterior(n, answers, eps_hat)
    best = int(np.argmax(post))
    if post[best] >= 1.0 - delta or len(answers) >= budget:
        return Placed(best)
    return Query(posterior_median_position(post))


class BisectionInsertion(Strategy):
    name = "bisection"

    def __init__(self, eps_hat: float = DEFAULT_EPS, delta: float = DEFAULT_DELTA) -> None:
        if not 0.0 < eps_hat < 0.5:
            raise ValueError(f"eps_hat must be in (0, 0.5), got {eps_hat}")
        if not 0.0 < delta < 1.0:
            raise ValueError(f"delta must be in (0, 1), got {delta}")
        self.eps_hat = eps_hat
        self.delta = delta

    def _next(self, state: InsertionState) -> Step:
        return bisection_step(
            state.n, state.answers, self.eps_hat, self.delta, question_budget(state.n)
        )
