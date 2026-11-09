"""Simulated users with known true utilities (docs/conventions.md, "Simulated users")."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

DEFAULT_K = 8


@dataclass(frozen=True)
class Population:
    """Restaurants and users. U[u, j] = quality[j] + tastes[u] @ factors[j]."""

    quality: FloatArray  # (R,)
    factors: FloatArray  # (R, k)
    tastes: FloatArray  # (U, k)

    @property
    def n_restaurants(self) -> int:
        return int(self.quality.shape[0])

    @property
    def n_users(self) -> int:
        return int(self.tastes.shape[0])

    def utilities(self, user: int) -> FloatArray:
        """True utility of every restaurant for one user, shape (R,)."""
        return np.asarray(self.quality + self.factors @ self.tastes[user], dtype=np.float64)


def make_population(
    n_restaurants: int, n_users: int, rng: np.random.Generator, k: int = DEFAULT_K
) -> Population:
    if n_restaurants < 2 or n_users < 1 or k < 1:
        raise ValueError("need at least 2 restaurants, 1 user and k >= 1")
    quality = rng.standard_normal(n_restaurants)
    factors = rng.standard_normal((n_restaurants, k))
    tastes = rng.standard_normal((n_users, k)) / np.sqrt(k)
    return Population(quality=quality, factors=factors, tastes=tastes)


def random_pair_deltas(pop: Population, n_pairs: int, rng: np.random.Generator) -> FloatArray:
    """U[u, i] - U[u, j] for random users u and random distinct restaurants i != j."""
    users = rng.integers(0, pop.n_users, size=n_pairs)
    i = rng.integers(0, pop.n_restaurants, size=n_pairs)
    # j uniform over the other R - 1 restaurants
    j = (i + rng.integers(1, pop.n_restaurants, size=n_pairs)) % pop.n_restaurants
    taste = pop.tastes[users]
    u_i = pop.quality[i] + np.einsum("pk,pk->p", pop.factors[i], taste)
    u_j = pop.quality[j] + np.einsum("pk,pk->p", pop.factors[j], taste)
    return np.asarray(u_i - u_j, dtype=np.float64)
