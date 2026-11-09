import numpy as np
import pytest

from pairrank.sim.noise import (
    BradleyTerryNoise,
    ConstantNoise,
    StickyNoise,
    bt_error_prob,
    calibrate_bt_temperature,
)
from pairrank.sim.users import make_population, random_pair_deltas


def test_constant_noise_error_rate() -> None:
    rng = np.random.default_rng(11)
    noise = ConstantNoise(0.1)
    wrong = sum(not noise.answer(1.0, 0.0, rng) for _ in range(1_000_000))
    assert abs(wrong / 1_000_000 - 0.1) < 0.002


@pytest.mark.parametrize("target", [0.05, 0.1, 0.2, 0.3])
def test_bt_calibration_hits_the_target_on_fresh_pairs(target: float) -> None:
    pop = make_population(1000, 2000, np.random.default_rng(1))
    temperature = calibrate_bt_temperature(
        target, random_pair_deltas(pop, 200_000, np.random.default_rng(2))
    )
    rng = np.random.default_rng(3)
    deltas = random_pair_deltas(pop, 1_000_000, rng)
    wrong = rng.random(deltas.shape[0]) < bt_error_prob(np.abs(deltas), temperature)
    assert abs(float(wrong.mean()) - target) < 0.002


def test_bt_scalar_matches_vectorized() -> None:
    noise = BradleyTerryNoise(0.7)
    for d in [-30.0, -1.0, -0.1, 0.1, 1.0, 30.0]:
        p_wrong = noise.p_report_better(0.0, abs(d))  # new is truly worse by |d|
        assert p_wrong == pytest.approx(float(bt_error_prob(np.array([abs(d)]), 0.7)[0]))


def test_bt_closer_pairs_are_noisier() -> None:
    noise = BradleyTerryNoise(1.0)
    assert noise.p_report_better(0.1, 0.0) < noise.p_report_better(2.0, 0.0)


def test_sticky_with_rho_one_always_repeats() -> None:
    rng = np.random.default_rng(5)
    noise = StickyNoise(ConstantNoise(0.4), rho=1.0)
    first = noise.answer(1.0, 0.0, rng, pair=(7, 3))
    assert all(noise.answer(1.0, 0.0, rng, pair=(7, 3)) == first for _ in range(100))
    # the reversed orientation gives the consistent (opposite) answer
    assert noise.answer(0.0, 1.0, rng, pair=(3, 7)) == (not first)


def test_sticky_with_rho_zero_is_the_base_model() -> None:
    rng = np.random.default_rng(6)
    noise = StickyNoise(ConstantNoise(0.1), rho=0.0)
    wrong = sum(not noise.answer(1.0, 0.0, rng, pair=(1, 2)) for _ in range(200_000))
    assert abs(wrong / 200_000 - 0.1) < 0.003


def test_sticky_needs_pair_ids() -> None:
    with pytest.raises(ValueError):
        StickyNoise(ConstantNoise(0.1), 0.5).answer(1.0, 0.0, np.random.default_rng(0))
