import numpy as np
import pytest

from pairrank import conventions as c
from pairrank.sim.session import true_slot
from pairrank.strategies import BinaryInsertion, Placed


def test_best_position_is_zero_and_displays_as_rank_one() -> None:
    assert c.BEST_POSITION == 0
    assert c.display_rank(c.BEST_POSITION) == 1


def test_display_rank_rejects_negative_positions() -> None:
    with pytest.raises(ValueError):
        c.display_rank(-1)


def test_score_range() -> None:
    assert (c.SCORE_MIN, c.SCORE_MAX) == (0.0, 10.0)


def test_tier_bands_tile_the_score_range_in_order() -> None:
    bands = [c.TIER_BANDS[t] for t in ("disliked", "fine", "liked")]
    assert bands[0][0] == c.SCORE_MIN
    assert bands[-1][1] == c.SCORE_MAX
    for (_, hi), (lo, _) in zip(bands, bands[1:], strict=False):
        assert hi == lo


def test_inserting_into_empty_list_gives_slot_zero() -> None:
    strategy = BinaryInsertion()
    assert strategy.next_query(strategy.start(0)) == Placed(0)


@pytest.mark.parametrize("n", [1, 2, 5, 10])
def test_correct_answer_meaning(n: int) -> None:
    # "new is better than position j" is correct exactly when the true slot is <= j.
    list_u = np.arange(n, 0, -1, dtype=np.float64)  # position 0 = best (highest utility)
    for r in range(n + 1):
        u_new = n - r + 0.5  # truly belongs in slot r
        assert true_slot(list_u, u_new) == r
        for j in range(n):
            truly_better = u_new > list_u[j]
            assert truly_better == (r <= j)


def test_display_score_rounds_to_one_decimal() -> None:
    assert c.display_score(7.349) == 7.3
    assert c.display_score(7.351) == 7.4
