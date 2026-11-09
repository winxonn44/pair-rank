import numpy as np
import pytest
from scipy.stats import norm

from pairrank.conventions import TIER_BANDS
from pairrank.drift import (
    expected_churn,
    mean_abs_drift,
    score_history,
    true_scores,
    true_tier,
    visible_churn,
)
from pairrank.scoring import percentile_delta, percentile_scores, tier_scores
from pairrank.sim.noise import ConstantNoise
from pairrank.strategies import BinaryInsertion


def test_percentile_endpoints_and_order() -> None:
    s = percentile_scores(5)
    assert s[0] == 10.0 and s[-1] == 0.0
    assert np.all(np.diff(s) < 0)
    assert percentile_scores(1).tolist() == [10.0]
    assert percentile_scores(0).size == 0


@pytest.mark.parametrize("n", range(2, 101))
def test_single_insertion_delta_matches_the_closed_form(n: int) -> None:
    """S2 'done when': the change from one insertion equals the formula to 1e-12."""
    before = percentile_scores(n)
    for slot in range(n + 1):
        after = np.delete(percentile_scores(n + 1), slot)
        np.testing.assert_allclose(after - before, percentile_delta(n, slot), atol=1e-12, rtol=0)


@pytest.mark.parametrize("tier", ["disliked", "fine", "liked"])
@pytest.mark.parametrize("m", [1, 2, 7, 40])
def test_tier_scores_stay_in_band_and_descend(tier: str, m: int) -> None:
    lo, hi = TIER_BANDS[tier]  # type: ignore[index]
    s = tier_scores(tier, m)  # type: ignore[arg-type]
    assert np.all((s > lo) & (s < hi))
    assert np.all(np.diff(s) < 0)


def test_true_tier_thresholds() -> None:
    assert true_tier(float(norm.ppf(0.2))) == "disliked"
    assert true_tier(0.0) == "fine"
    assert true_tier(float(norm.ppf(0.9))) == "liked"


def test_true_scores_are_ten_times_the_quantile() -> None:
    np.testing.assert_allclose(true_scores(np.array([0.0])), [5.0])


@pytest.mark.parametrize("mapping", ["percentile", "tiered"])
def test_history_shape_nan_before_arrival_and_noise_free_is_sorted(mapping: str) -> None:
    rng = np.random.default_rng(1)
    u = rng.standard_normal(30)
    h = score_history(BinaryInsertion(), u, ConstantNoise(0.0), rng, mapping)  # type: ignore[arg-type]
    assert np.isnan(h[0, 1:]).all() and not np.isnan(h[-1]).any()
    if mapping == "percentile":
        # with no noise, a higher utility always has a higher score
        order = np.argsort(u)
        assert np.all(np.diff(h[-1][order]) > 0)


def test_drift_and_churn_on_a_small_known_history() -> None:
    h = np.array([[10.0, np.nan], [10.0, 0.0]])
    assert mean_abs_drift(h, 0, 1) == 0.0
    assert visible_churn(h, 1) == 0.0
    h2 = np.array([[5.0, np.nan], [7.0, 0.0]])
    assert mean_abs_drift(h2, 0, 1) == 2.0
    assert visible_churn(h2, 1) == 1.0


def test_expected_churn_falls_as_lists_grow() -> None:
    values = [expected_churn(n) for n in (10, 25, 49, 100)]
    assert values == sorted(values, reverse=True)
    assert 0.5 < expected_churn(49) < 0.7
