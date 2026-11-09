"""S4: binary insertion, then check the two neighbors; investigate only on a contradiction.

Consistent users pay at most two extra questions. If either neighbor disagrees with
the chosen slot, the strategy switches to probabilistic bisection, starting from the
posterior given every answer so far.
"""

from __future__ import annotations

from pairrank.conventions import DEFAULT_EPS
from pairrank.state import Answer, InsertionState
from pairrank.strategies.base import Placed, Query, Step, Strategy
from pairrank.strategies.bisection import DEFAULT_DELTA, bisection_step, question_budget


def _binary_prefix(n: int, answers: tuple[Answer, ...]) -> tuple[int | None, int]:
    """Replay binary insertion. Returns (chosen slot or None if unfinished, answers used)."""
    lo, hi = 0, n
    used = 0
    while lo < hi:
        if used == len(answers):
            return None, used
        new_is_better = answers[used][1]
        mid = (lo + hi) // 2
        used += 1
        if new_is_better:
            hi = mid
        else:
            lo = mid + 1
    return lo, used


def neighbor_checks(slot: int, n: int) -> list[tuple[int, bool]]:
    """(position, expected answer) for the entries just above and just below `slot`."""
    checks: list[tuple[int, bool]] = []
    if slot > 0:
        checks.append((slot - 1, False))  # the entry above should beat the new place
    if slot < n:
        checks.append((slot, True))  # the new place should beat the entry below
    return checks


class VerifyInsertion(Strategy):
    name = "verify"

    def __init__(self, eps_hat: float = DEFAULT_EPS, delta: float = DEFAULT_DELTA) -> None:
        self.eps_hat = eps_hat
        self.delta = delta

    def contradicted(self, state: InsertionState) -> bool:
        """True once a neighbor check has disagreed with binary insertion's slot."""
        slot, used = _binary_prefix(state.n, state.answers)
        if slot is None:
            return False
        checks = neighbor_checks(slot, state.n)
        done = state.answers[used : used + len(checks)]
        return any(
            better != expected for (_, better), (_, expected) in zip(done, checks, strict=False)
        )

    def _next(self, state: InsertionState) -> Step:
        n = state.n
        slot, used = _binary_prefix(n, state.answers)
        if slot is None:
            lo, hi = 0, n
            for _, better in state.answers:
                mid = (lo + hi) // 2
                lo, hi = (lo, mid) if better else (mid + 1, hi)
            return Query((lo + hi) // 2)
        if self.contradicted(state):
            budget = question_budget(n) + 2
            return bisection_step(n, state.answers, self.eps_hat, self.delta, budget)
        checks = neighbor_checks(slot, n)
        asked = len(state.answers) - used
        if asked < len(checks):
            return Query(checks[asked][0])
        return Placed(slot)
