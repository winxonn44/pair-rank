import itertools
import math

import numpy as np
import pytest
from scipy import stats as sps

from pairrank.oracle import (
    enumerate_binary_insertion,
    exact_slot_posterior,
    kendall_tau_bruteforce,
    mean_abs_error,
    signed_error_pmf,
)
from pairrank.sim.noise import ConstantNoise
from pairrank.sim.session import simulate_insertions
from pairrank.stats import chi2_against_pmf
from pairrank.strategies import BinaryInsertion

Q1_SIZES = [9, 19, 49, 99]
Q1_EPS = [0.05, 0.1, 0.2, 0.3]


def _patterns_oracle(n: int, eps: float) -> np.ndarray:
    """A second, independent oracle: loop over every pattern of right/wrong answers."""
    depth = math.ceil(math.log2(n + 1)) if n > 0 else 0
    p = np.zeros((n + 1, n + 1))
    for r in range(n + 1):
        for pattern in itertools.product([True, False], repeat=depth):
            lo, hi, prob, used = 0, n, 1.0, 0
            while lo < hi:
                mid = (lo + hi) // 2
                right = pattern[used]
                used += 1
                prob *= (1 - eps) if right else eps
                says_better = (r <= mid) == right
                lo, hi = (lo, mid) if says_better else (mid + 1, hi)
            if all(pattern[used:]):  # count each search path once
                p[r, lo] += prob
    return p


@pytest.mark.parametrize("n", [0, 1, 2, 3, 7, 8, 12, 49])
@pytest.mark.parametrize("eps", [0.0, 0.1, 0.3])
def test_two_oracles_agree(n: int, eps: float) -> None:
    np.testing.assert_allclose(
        enumerate_binary_insertion(n, eps), _patterns_oracle(n, eps), atol=1e-15
    )


@pytest.mark.parametrize("n", [0, 5, 49, 100])
def test_rows_are_distributions_and_noise_free_is_identity(n: int) -> None:
    p = enumerate_binary_insertion(n, 0.2)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, atol=1e-12)
    np.testing.assert_array_equal(enumerate_binary_insertion(n, 0.0), np.eye(n + 1))


def test_exact_mean_errors_match_the_design_doc() -> None:
    # Design doc B2: exact values 0.64, 1.22, 2.89, 5.65 at eps = 0.1.
    got = [mean_abs_error(enumerate_binary_insertion(n, 0.1)) for n in Q1_SIZES]
    np.testing.assert_allclose(got, [0.64, 1.22, 2.89, 5.65], atol=0.006)


@pytest.mark.parametrize("n", Q1_SIZES)
@pytest.mark.parametrize("eps", Q1_EPS)
def test_simulation_matches_exact_oracle(n: int, eps: float) -> None:
    """S0 'done when': simulated binary insertion agrees with exact enumeration."""
    rng = np.random.default_rng([20261106, n, int(eps * 100)])
    results = simulate_insertions(BinaryInsertion(), n, ConstantNoise(eps), 2000, rng)
    errors = np.array([r.error for r in results], dtype=float)
    p = enumerate_binary_insertion(n, eps)
    exact = mean_abs_error(p)
    se = errors.std(ddof=1) / math.sqrt(len(errors))
    assert abs(errors.mean() - exact) < 3 * se, (errors.mean(), exact, se)
    _, _, pvalue = chi2_against_pmf([r.slot - r.true_slot for r in results], signed_error_pmf(p))
    assert pvalue > 0.001


def test_posterior_with_no_answers_is_uniform() -> None:
    np.testing.assert_allclose(exact_slot_posterior([], 9, 0.1), np.full(10, 0.1))


def test_posterior_matches_hand_computation() -> None:
    # n = 3, slots 0..3; one answer "better than position 1" (correct iff slot <= 1).
    post = exact_slot_posterior([(1, True)], 3, 0.1)
    np.testing.assert_allclose(post, np.array([0.9, 0.9, 0.1, 0.1]) / 2.0)


def test_noise_free_posterior_concentrates_on_the_true_slot() -> None:
    n, r = 20, 13
    answers = [(j, r <= j) for j in range(n)]
    post = exact_slot_posterior(answers, n, 1e-12)
    assert int(np.argmax(post)) == r
    assert post[r] > 1 - 1e-9


def test_kendall_bruteforce_matches_scipy() -> None:
    rng = np.random.default_rng(3)
    for _ in range(1000):
        m = int(rng.integers(2, 30))
        x, y = rng.permutation(m), rng.permutation(m)
        expected = float(sps.kendalltau(x, y).statistic)
        assert kendall_tau_bruteforce(x.tolist(), y.tolist()) == pytest.approx(expected, abs=1e-12)
