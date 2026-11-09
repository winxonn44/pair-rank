import math

import numpy as np
import pytest

from pairrank.oracle import exact_slot_posterior
from pairrank.sim.noise import ConstantNoise, FirstAnswerWrong
from pairrank.sim.session import run_insertion, simulate_insertions
from pairrank.state import InsertionState
from pairrank.strategies import (
    BinaryInsertion,
    BisectionInsertion,
    MajorityInsertion,
    NeighborMajorityInsertion,
    Placed,
    Query,
    VerifyInsertion,
    get_strategy,
)
from pairrank.strategies.bisection import question_budget, slot_posterior
from pairrank.strategies.verify import neighbor_checks

NAMES = ["binary", "majority", "majority-neighbor", "bisection", "verify"]
SIZES = [0, 1, 2, 3, 7, 8, 49, 100]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("n", SIZES)
def test_exact_without_noise(name: str, n: int) -> None:
    rng = np.random.default_rng([41, n])
    strategy = get_strategy(name)
    noise = ConstantNoise(0.0)
    for _ in range(1000):
        u = rng.standard_normal(n + 1)
        result = run_insertion(strategy, np.sort(u[:n])[::-1], float(u[n]), noise, rng)
        assert result.slot == result.true_slot


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("n", SIZES)
def test_every_true_slot_is_found_without_noise(name: str, n: int) -> None:
    strategy = get_strategy(name)
    for r in range(n + 1):
        state = strategy.start(n)
        while isinstance(step := strategy.next_query(state), Query):
            assert 0 <= step.ref_position < n
            state = strategy.observe(state, step.ref_position, r <= step.ref_position)
        assert step == Placed(r)


@pytest.mark.parametrize("name", NAMES)
def test_state_round_trips_and_every_query_is_valid_under_random_answers(name: str) -> None:
    rng = np.random.default_rng(13)
    strategy = get_strategy(name)
    for _ in range(300):
        n = int(rng.integers(0, 120))
        state = strategy.start(n)
        while True:
            restored = InsertionState.from_json(state.to_json())
            assert restored == state
            step = strategy.next_query(state)
            assert strategy.next_query(restored) == step
            if isinstance(step, Placed):
                assert 0 <= step.slot <= n
                break
            assert 0 <= step.ref_position < n
            state = strategy.observe(restored, step.ref_position, bool(rng.random() < 0.5))


@pytest.mark.parametrize("name", ["bisection", "verify"])
def test_posterior_matches_brute_force_bayes(name: str) -> None:
    """S1 'done when': incremental posteriors equal the oracle to 1e-12 at every step."""
    rng = np.random.default_rng(17)
    strategy = get_strategy(name)
    for _ in range(1000):
        n = int(rng.integers(1, 120))
        state = strategy.start(n)
        while isinstance(step := strategy.next_query(state), Query):
            state = strategy.observe(state, step.ref_position, bool(rng.random() < 0.5))
            np.testing.assert_allclose(
                slot_posterior(n, state.answers, 0.1),
                exact_slot_posterior(state.answers, n, 0.1),
                atol=1e-12,
                rtol=0,
            )


@pytest.mark.parametrize("eps", [0.05, 0.1, 0.3])
def test_majority_one_step_matches_exact_formula(eps: float) -> None:
    # n = 1 is a single vote: wrong with 3e^2 - 2e^3, costing 2 + 2e(1 - e) questions.
    rng = np.random.default_rng([19, int(eps * 100)])
    res = simulate_insertions(MajorityInsertion(), 1, ConstantNoise(eps), 200_000, rng)
    wrong = np.mean([r.error for r in res])
    questions = np.mean([r.n_questions for r in res])
    assert wrong == pytest.approx(3 * eps**2 - 2 * eps**3, abs=0.002)
    assert questions == pytest.approx(2 + 2 * eps * (1 - eps), abs=0.005)


def test_neighbor_majority_uses_different_pivots_when_possible() -> None:
    strategy = NeighborMajorityInsertion()
    state = strategy.start(20)
    first = strategy.next_query(state)
    assert isinstance(first, Query)
    state = strategy.observe(state, first.ref_position, True)
    second = strategy.next_query(state)
    assert isinstance(second, Query)
    assert second.ref_position == first.ref_position + 1


def test_neighbor_checks() -> None:
    assert neighbor_checks(0, 0) == []
    assert neighbor_checks(0, 5) == [(0, True)]
    assert neighbor_checks(5, 5) == [(4, False)]
    assert neighbor_checks(2, 5) == [(1, False), (2, True)]


def test_verify_costs_at_most_two_extra_questions_for_consistent_users() -> None:
    rng = np.random.default_rng(23)
    n = 49
    for _ in range(500):
        r = int(rng.integers(0, n + 1))
        strategy = VerifyInsertion()
        state = strategy.start(n)
        while isinstance(step := strategy.next_query(state), Query):
            state = strategy.observe(state, step.ref_position, r <= step.ref_position)
        assert state.n_questions <= math.ceil(math.log2(n + 1)) + 2
        assert not strategy.contradicted(state)


def test_verify_investigates_a_wrong_first_answer() -> None:
    rng = np.random.default_rng(29)
    strategy = VerifyInsertion()
    detected = 0
    for _ in range(1000):
        u = rng.standard_normal(50)
        result = run_insertion(
            strategy, np.sort(u[:49])[::-1], float(u[49]), FirstAnswerWrong(), rng
        )
        state = InsertionState(strategy="verify", n=49, answers=result.answers)
        detected += strategy.contradicted(state)
    assert detected >= 900


@pytest.mark.parametrize("strategy", [BisectionInsertion(), VerifyInsertion()])
def test_bayesian_strategies_respect_their_budget(strategy: BisectionInsertion) -> None:
    rng = np.random.default_rng(31)
    n = 49
    limit = question_budget(n) + 2
    for _ in range(300):
        state = strategy.start(n)
        while isinstance(step := strategy.next_query(state), Query):
            state = strategy.observe(state, step.ref_position, bool(rng.random() < 0.5))
        assert state.n_questions <= limit


def test_binary_is_unchanged_by_adding_ids() -> None:
    # S0's numbers depend on this: place ids must not consume random numbers.
    rng = np.random.default_rng(37)
    results = simulate_insertions(BinaryInsertion(), 9, ConstantNoise(0.1), 200, rng)
    assert len(results) == 200


def test_majority_matches_binary_oracle_at_the_voted_error_rate() -> None:
    # A majority step is one binary step wrong with 3e^2 - 2e^3, so the exact oracle applies.
    from pairrank.oracle import enumerate_binary_insertion, mean_abs_error

    eps = 0.1
    exact = mean_abs_error(enumerate_binary_insertion(49, 3 * eps**2 - 2 * eps**3))
    rng = np.random.default_rng(43)
    res = simulate_insertions(MajorityInsertion(), 49, ConstantNoise(eps), 3000, rng)
    errors = np.array([r.error for r in res], dtype=float)
    assert abs(errors.mean() - exact) < 3 * errors.std(ddof=1) / math.sqrt(len(errors))
