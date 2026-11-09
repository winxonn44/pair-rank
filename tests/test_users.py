import numpy as np

from pairrank.sim.users import make_population, random_pair_deltas


def test_utility_variance_is_two() -> None:
    pop = make_population(4000, 4000, np.random.default_rng(0))
    u = np.stack([pop.utilities(i) for i in range(0, 4000, 10)])
    assert abs(float(u.var()) - 2.0) < 0.1


def test_pair_deltas_never_compare_a_place_with_itself() -> None:
    pop = make_population(5, 3, np.random.default_rng(1))
    deltas = random_pair_deltas(pop, 10_000, np.random.default_rng(2))
    assert np.all(deltas != 0.0)


def test_pair_delta_variance_is_four() -> None:
    # Var(U_i - U_j) = 2 Var(g) + 2 E[(a . b)^2] = 2 + 2 over a large population.
    pop = make_population(4000, 4000, np.random.default_rng(3))
    deltas = random_pair_deltas(pop, 200_000, np.random.default_rng(4))
    assert abs(float(deltas.var()) - 4.0) < 0.15


def test_population_is_reproducible_by_seed() -> None:
    a = make_population(50, 10, np.random.default_rng(9))
    b = make_population(50, 10, np.random.default_rng(9))
    np.testing.assert_array_equal(a.utilities(3), b.utilities(3))
