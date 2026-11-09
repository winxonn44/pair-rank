"""S1: binary insertion. At most ceil(log2(n + 1)) questions; never re-asks."""

from __future__ import annotations

from pairrank.state import InsertionState
from pairrank.strategies.base import Placed, Query, Step, Strategy


def binary_interval(n: int, answers: tuple[tuple[int, bool], ...]) -> tuple[int, int]:
    """The slot interval [lo, hi] left after `answers`, assuming each was the midpoint."""
    lo, hi = 0, n
    for j, new_is_better in answers:
        if new_is_better:
            hi = j  # true slot <= j
        else:
            lo = j + 1  # true slot > j
    return lo, hi


class BinaryInsertion(Strategy):
    name = "binary"

    def _next(self, state: InsertionState) -> Step:
        lo, hi = binary_interval(state.n, state.answers)
        if lo >= hi:
            return Placed(lo)
        return Query((lo + hi) // 2)
