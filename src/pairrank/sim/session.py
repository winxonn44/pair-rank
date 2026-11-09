"""Run simulated insertions: a strategy asks, a noise model answers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pairrank.sim.noise import NoiseModel
from pairrank.state import Answer
from pairrank.strategies.base import Placed, Strategy


@dataclass(frozen=True)
class InsertionResult:
    strategy: str
    n: int
    slot: int
    true_slot: int
    answers: tuple[Answer, ...]
    n_wrong: int = 0  # answers that disagreed with the true utilities

    @property
    def n_questions(self) -> int:
        return len(self.answers)

    @property
    def error(self) -> int:
        return abs(self.slot - self.true_slot)


def true_slot(list_utilities: NDArray[np.float64], new_utility: float) -> int:
    """Number of current entries the new place is truly worse than."""
    return int(np.count_nonzero(list_utilities > new_utility))


def run_insertion(
    strategy: Strategy,
    list_utilities: NDArray[np.float64],
    new_utility: float,
    noise: NoiseModel,
    rng: np.random.Generator,
    *,
    seed: int = 0,
    list_ids: NDArray[np.int64] | None = None,
    new_id: int = -1,
) -> InsertionResult:
    """Insert one place into a list whose entries (in list order) have these true utilities."""
    n = int(list_utilities.shape[0])
    state = strategy.start(n, seed)
    max_questions = 20 * (n + 2)  # guard against a strategy that never stops
    n_wrong = 0
    while True:
        step = strategy.next_query(state)
        if isinstance(step, Placed):
            break
        if state.n_questions >= max_questions:
            raise RuntimeError(f"{strategy.name} asked more than {max_questions} questions")
        j = step.ref_position
        pair = (new_id, int(list_ids[j])) if list_ids is not None else None
        said_better = noise.answer(new_utility, float(list_utilities[j]), rng, pair)
        n_wrong += said_better != bool(new_utility > list_utilities[j])
        state = strategy.observe(state, j, said_better)
    return InsertionResult(
        strategy=strategy.name,
        n=n,
        slot=step.slot,
        true_slot=true_slot(list_utilities, new_utility),
        answers=state.answers,
        n_wrong=n_wrong,
    )


def simulate_insertions(
    strategy: Strategy,
    n: int,
    noise: NoiseModel,
    n_insertions: int,
    rng: np.random.Generator,
) -> list[InsertionResult]:
    """Insertions into a correctly ordered list of n i.i.d. N(0, 1) utilities.

    The new place's true slot is then uniform on {0, ..., n}, which is what the
    exact oracle assumes.
    """
    results = []
    for _ in range(n_insertions):
        u = rng.standard_normal(n + 1)
        ids = np.argsort(-u[:n], kind="stable").astype(np.int64)  # position 0 = best
        results.append(
            run_insertion(strategy, u[ids], float(u[n]), noise.fresh(), rng, list_ids=ids, new_id=n)
        )
    return results


@dataclass(frozen=True)
class ListBuild:
    order: tuple[int, ...]  # place ids, best first
    n_questions: int
    n_wrong: int


def build_list(
    strategy: Strategy,
    utilities: NDArray[np.float64],
    noise: NoiseModel,
    rng: np.random.Generator,
) -> ListBuild:
    """One simulated user builds a whole list, inserting places in index order.

    Later places are compared against the list as it stands, mistakes included.
    """
    user_noise = noise.fresh()
    order: list[int] = []
    questions = wrong = 0
    for new_id in range(utilities.shape[0]):
        ids = np.asarray(order, dtype=np.int64)
        result = run_insertion(
            strategy,
            utilities[ids],
            float(utilities[new_id]),
            user_noise,
            rng,
            list_ids=ids,
            new_id=new_id,
        )
        order.insert(result.slot, new_id)
        questions += result.n_questions
        wrong += result.n_wrong
    return ListBuild(order=tuple(order), n_questions=questions, n_wrong=wrong)
