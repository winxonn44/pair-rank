import numpy as np

from pairrank.sim.noise import ConstantNoise, StickyNoise
from pairrank.sim.session import run_insertion, simulate_insertions, true_slot
from pairrank.strategies import BinaryInsertion


def test_true_slot_counts_entries_that_are_truly_better() -> None:
    list_u = np.array([5.0, 3.0, 1.0])
    assert [true_slot(list_u, u) for u in (6.0, 4.0, 2.0, 0.0)] == [0, 1, 2, 3]


def test_true_slot_ignores_list_order() -> None:
    # The list may be misordered; the true slot is defined by utilities only.
    assert true_slot(np.array([1.0, 5.0, 3.0]), 4.0) == 1


def test_true_slots_are_uniform() -> None:
    rng = np.random.default_rng(4)
    results = simulate_insertions(BinaryInsertion(), 9, ConstantNoise(0.0), 20_000, rng)
    counts = np.bincount([r.true_slot for r in results], minlength=10)
    assert np.all(np.abs(counts / 20_000 - 0.1) < 0.01)


def test_simulation_is_reproducible_by_seed() -> None:
    def run() -> list[tuple[int, int]]:
        rng = np.random.default_rng(12)
        res = simulate_insertions(BinaryInsertion(), 30, ConstantNoise(0.2), 300, rng)
        return [(r.slot, r.true_slot) for r in res]

    assert run() == run()


def test_run_insertion_passes_place_ids_to_sticky_noise() -> None:
    rng = np.random.default_rng(8)
    result = run_insertion(
        BinaryInsertion(),
        np.array([3.0, 2.0, 1.0]),
        1.5,
        StickyNoise(ConstantNoise(0.1), 0.7),
        rng,
        list_ids=np.array([10, 11, 12]),
        new_id=99,
    )
    assert 0 <= result.slot <= 3
