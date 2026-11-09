import numpy as np
import pytest
from scipy import stats as sps

from pairrank.metrics import (
    kendall_tau,
    list_tau,
    posterior_median_slot,
    tau_after_single_error,
)
from pairrank.oracle import kendall_tau_bruteforce
from pairrank.sim.noise import ConstantNoise, FirstAnswerWrong, StickyNoise
from pairrank.sim.session import build_list
from pairrank.strategies import BinaryInsertion


def test_kendall_fast_matches_brute_force_and_scipy() -> None:
    rng = np.random.default_rng(3)
    for _ in range(1000):
        m = int(rng.integers(2, 60))
        x, y = rng.permutation(m).tolist(), rng.permutation(m).tolist()
        fast = kendall_tau(x, y)
        assert fast == pytest.approx(kendall_tau_bruteforce(x, y), abs=1e-12)
        assert fast == pytest.approx(float(sps.kendalltau(x, y).statistic), abs=1e-12)


def test_list_tau_extremes() -> None:
    utilities = np.array([3.0, 2.0, 1.0, 0.0])
    assert list_tau([0, 1, 2, 3], utilities) == 1.0
    assert list_tau([3, 2, 1, 0], utilities) == -1.0


@pytest.mark.parametrize("d", [1, 3, 7])
def test_single_displacement_formula(d: int) -> None:
    utilities = np.arange(20, 0, -1, dtype=float)
    order = list(range(20))
    order.insert(d, order.pop(0))  # move the best entry down d positions
    assert list_tau(order, utilities) == pytest.approx(tau_after_single_error(d, 20))


def test_posterior_median_slot() -> None:
    assert posterior_median_slot(np.array([0.1, 0.2, 0.3, 0.4])) == 2
    assert posterior_median_slot(np.array([1.0, 0.0])) == 0


def test_noise_free_list_is_perfect() -> None:
    rng = np.random.default_rng(5)
    utilities = rng.standard_normal(40)
    built = build_list(BinaryInsertion(), utilities, ConstantNoise(0.0), rng)
    assert list_tau(built.order, utilities) == 1.0
    assert sorted(built.order) == list(range(40))
    assert built.n_wrong == 0


def test_build_list_uses_one_memory_per_user() -> None:
    noise = StickyNoise(ConstantNoise(0.1), 0.7)
    rng = np.random.default_rng(6)
    build_list(BinaryInsertion(), rng.standard_normal(10), noise, rng)
    assert noise._memory == {}  # the template instance stays clean


def test_first_answer_wrong_only_flips_the_first_answer() -> None:
    noise = FirstAnswerWrong()
    assert noise.p_report_better(1.0, 0.0) == 0.0
    assert noise.p_report_better(1.0, 0.0) == 1.0
    assert noise.fresh().p_report_better(1.0, 0.0) == 0.0
