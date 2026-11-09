"""S2: noisy binary search that re-asks on conflict (majority of up to 3 votes per step).

Each step of the binary search votes on "is the true slot <= mid?". Two votes that
agree decide it; if they disagree, a third breaks the tie.

- `MajorityInsertion` (S2) asks about the same pair every time.
- `NeighborMajorityInsertion` (S2b) asks about an adjacent pivot for the later votes,
  the defense against a user who repeats the same wrong answer about one pair.
"""

from __future__ import annotations

from pairrank.state import InsertionState
from pairrank.strategies.base import Placed, Query, Step, Strategy


def _same_pivots(lo: int, hi: int, mid: int) -> tuple[int, int, int]:
    return mid, mid, mid


def _neighbor_pivots(lo: int, hi: int, mid: int) -> tuple[int, int, int]:
    """Pivots for votes 1-3. Valid question positions in [lo, hi] are lo..hi-1.

    With correct answers the majority is always right. If the true slot is mid + 1,
    the votes at mid and mid + 1 disagree legitimately, and the third vote (at
    mid - 1, or mid when that is out of range) correctly says "not <= mid". If the
    second vote had to use mid - 1 and the true slot is mid, the third vote at mid
    correctly says "<= mid".
    """
    if mid + 1 <= hi - 1:
        return mid, mid + 1, (mid - 1 if mid - 1 >= lo else mid)
    if mid - 1 >= lo:
        return mid, mid - 1, mid
    return mid, mid, mid


class MajorityInsertion(Strategy):
    name = "majority"
    _pivots = staticmethod(_same_pivots)

    def _next(self, state: InsertionState) -> Step:
        lo, hi = 0, state.n
        answers = state.answers
        i = 0
        while lo < hi:
            mid = (lo + hi) // 2
            pivots = self._pivots(lo, hi, mid)
            votes = [better for _, better in answers[i : i + 3]]
            if len(votes) < 2:
                return Query(pivots[len(votes)])
            if votes[0] == votes[1]:
                decision, used = votes[0], 2
            elif len(votes) < 3:
                return Query(pivots[2])
            else:
                decision, used = votes[2], 3  # votes 1 and 2 split, so vote 3 is the majority
            i += used
            if decision:
                hi = mid
            else:
                lo = mid + 1
        return Placed(lo)


class NeighborMajorityInsertion(MajorityInsertion):
    name = "majority-neighbor"
    _pivots = staticmethod(_neighbor_pivots)
