import numpy as np
import pytest
from scipy import stats as sps
from statsmodels.stats.power import TTestIndPower

from pairrank.abtest import (
    SESSION_INSERTIONS,
    draw_user_means,
    n_per_arm,
    peeking_rate,
    rejection_rate,
    simulate_user,
    welch_pvalue,
)
from pairrank.sim.noise import ConstantNoise
from pairrank.strategies import BinaryInsertion


def test_formula_constant() -> None:
    assert n_per_arm(1.0, 0.2) == 393
    assert n_per_arm(1.0, 0.1) == 1570


@pytest.mark.parametrize("ratio", [0.1, 0.15, 0.2, 0.3])
def test_formula_matches_statsmodels_within_one_user(ratio: float) -> None:
    exact = TTestIndPower().solve_power(effect_size=ratio, alpha=0.05, power=0.8)
    assert abs(n_per_arm(1.0, ratio) - float(exact)) <= 1.0


def test_welch_matches_scipy() -> None:
    rng = np.random.default_rng(1)
    a, b = rng.normal(0, 1, 40), rng.normal(0.3, 2, 40)
    expected = sps.ttest_ind(a, b, equal_var=False).pvalue
    assert float(welch_pvalue(a, b)) == pytest.approx(float(expected))


def test_noise_free_user_has_no_error_and_no_audit_disagreement() -> None:
    out = simulate_user(BinaryInsertion(), ConstantNoise(0.0), np.random.default_rng(2))
    assert out.errors.shape == (SESSION_INSERTIONS,)
    assert out.errors.sum() == 0
    assert not out.audit_disagree.any()


def test_user_simulation_is_reproducible() -> None:
    def run() -> list[int]:
        rng = np.random.default_rng(3)
        return simulate_user(BinaryInsertion(), ConstantNoise(0.2), rng).errors.tolist()

    assert run() == run()


def _bank(mean: float, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).poisson(mean, (5000, 20)).astype(np.int64)


def test_partial_treatment_scales_the_effect() -> None:
    control, treatment = _bank(4.0, 4), _bank(2.0, 5)
    rng = np.random.default_rng(6)
    means = draw_user_means(control, treatment, 0.25, 40_000, rng)
    assert float(means.mean()) == pytest.approx(3.5, abs=0.02)


def test_aa_rate_and_power_behave() -> None:
    control, treatment = _bank(4.0, 7), _bank(2.0, 8)
    rng = np.random.default_rng(9)
    assert rejection_rate(control, None, 0.0, 100, 400, rng) < 0.10
    assert rejection_rate(control, treatment, 1.0, 100, 50, rng) == 1.0


def test_peeking_inflates_false_positives() -> None:
    control = _bank(4.0, 10)
    rng = np.random.default_rng(11)
    single = peeking_rate(control, 100, 800, rng, looks=1)
    many = peeking_rate(control, 100, 800, rng, looks=5)
    assert many > single
