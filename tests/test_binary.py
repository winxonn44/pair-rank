import math

import numpy as np
import pytest

from pairrank.sim.noise import ConstantNoise
from pairrank.sim.session import run_insertion
from pairrank.state import InsertionState
from pairrank.strategies import BinaryInsertion, Placed, Query, get_strategy

SIZES = [0, 1, 2, 3, 7, 8, 49, 100]


@pytest.mark.parametrize("n", SIZES)
def test_exact_without_noise(n: int) -> None:
    rng = np.random.default_rng(1000 + n)
    strategy = BinaryInsertion()
    noise = ConstantNoise(0.0)
    max_q = math.ceil(math.log2(n + 1)) if n > 0 else 0
    for _ in range(1000):
        u = rng.standard_normal(n + 1)
        list_u = np.sort(u[:n])[::-1]
        result = run_insertion(strategy, list_u, float(u[n]), noise, rng)
        assert result.slot == result.true_slot
        assert result.n_questions <= max_q


@pytest.mark.parametrize("n", SIZES)
def test_every_true_slot_is_reachable_without_noise(n: int) -> None:
    strategy = BinaryInsertion()
    for r in range(n + 1):
        state = strategy.start(n)
        while isinstance(step := strategy.next_query(state), Query):
            state = strategy.observe(state, step.ref_position, r <= step.ref_position)
        assert step == Placed(r)


def test_state_round_trips_through_json_at_every_step() -> None:
    rng = np.random.default_rng(7)
    strategy = BinaryInsertion()
    for _ in range(200):
        n = int(rng.integers(0, 120))
        state = strategy.start(n, seed=int(rng.integers(0, 2**31)))
        while True:
            restored = InsertionState.from_json(state.to_json())
            assert restored == state
            step = strategy.next_query(state)
            assert strategy.next_query(restored) == step
            if isinstance(step, Placed):
                break
            state = strategy.observe(restored, step.ref_position, bool(rng.random() < 0.5))


def test_observe_rejects_an_answer_to_a_different_question() -> None:
    strategy = BinaryInsertion()
    state = strategy.start(10)
    step = strategy.next_query(state)
    assert isinstance(step, Query)
    with pytest.raises(ValueError):
        strategy.observe(state, step.ref_position + 1, True)


def test_observe_rejects_answers_after_placement() -> None:
    strategy = BinaryInsertion()
    with pytest.raises(ValueError):
        strategy.observe(strategy.start(0), 0, True)


def test_state_from_another_strategy_is_rejected() -> None:
    with pytest.raises(ValueError):
        BinaryInsertion().next_query(InsertionState(strategy="other", n=3))


def test_registry() -> None:
    assert isinstance(get_strategy("binary"), BinaryInsertion)
    with pytest.raises(ValueError):
        get_strategy("nope")
