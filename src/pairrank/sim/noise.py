"""How simulated users answer "is the new place better?" (docs/conventions.md, "Noise models")."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray
from scipy.special import expit

Pair = tuple[int, int]  # (new place id, reference place id)


class NoiseModel(ABC):
    @abstractmethod
    def p_report_better(self, u_new: float, u_ref: float) -> float:
        """Probability the user says the new place is better."""

    def answer(
        self, u_new: float, u_ref: float, rng: np.random.Generator, pair: Pair | None = None
    ) -> bool:
        return bool(rng.random() < self.p_report_better(u_new, u_ref))


class ConstantNoise(NoiseModel):
    """M-const: every answer is wrong with probability eps."""

    def __init__(self, eps: float) -> None:
        if not 0.0 <= eps < 0.5:
            raise ValueError(f"eps must be in [0, 0.5), got {eps}")
        self.eps = eps

    def p_report_better(self, u_new: float, u_ref: float) -> float:
        return 1.0 - self.eps if u_new > u_ref else self.eps


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def bt_error_prob(abs_delta: NDArray[np.float64], temperature: float) -> NDArray[np.float64]:
    """P(wrong answer) = sigmoid(-|delta| / T), vectorized."""
    return np.asarray(expit(-abs_delta / temperature), dtype=np.float64)  # no overflow


class BradleyTerryNoise(NoiseModel):
    """M-BT: P(says new is better) = sigmoid((u_new - u_ref) / T). Close pairs are noisy."""

    def __init__(self, temperature: float) -> None:
        if temperature <= 0:
            raise ValueError(f"temperature must be > 0, got {temperature}")
        self.temperature = temperature

    def p_report_better(self, u_new: float, u_ref: float) -> float:
        return _sigmoid((u_new - u_ref) / self.temperature)


def calibrate_bt_temperature(target_eps: float, deltas: NDArray[np.float64]) -> float:
    """T such that the mean error over the given utility differences equals target_eps.

    The mean error sigmoid(-|delta|/T) increases with T, so bisect on log T.
    """
    if not 0.0 < target_eps < 0.5:
        raise ValueError(f"target_eps must be in (0, 0.5), got {target_eps}")
    abs_delta = np.abs(deltas)
    lo, hi = math.log(1e-6), math.log(1e6)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if float(np.mean(bt_error_prob(abs_delta, math.exp(mid)))) < target_eps:
            lo = mid
        else:
            hi = mid
    return math.exp(0.5 * (lo + hi))


class StickyNoise(NoiseModel):
    """M-sticky: a repeated pair repeats its earlier answer with probability rho.

    Remembers answers, so use one instance per simulated user. Answers are stored
    per unordered pair, as "the lower id wins", so either orientation is consistent.
    """

    def __init__(self, base: NoiseModel, rho: float) -> None:
        if not 0.0 <= rho <= 1.0:
            raise ValueError(f"rho must be in [0, 1], got {rho}")
        self.base = base
        self.rho = rho
        self._memory: dict[Pair, bool] = {}

    def p_report_better(self, u_new: float, u_ref: float) -> float:
        return self.base.p_report_better(u_new, u_ref)

    def answer(
        self, u_new: float, u_ref: float, rng: np.random.Generator, pair: Pair | None = None
    ) -> bool:
        if pair is None:
            raise ValueError("StickyNoise needs the pair of place ids")
        new_id, ref_id = pair
        key = (min(new_id, ref_id), max(new_id, ref_id))
        if key in self._memory and rng.random() < self.rho:
            low_wins = self._memory[key]
            return low_wins if new_id == key[0] else not low_wins
        said_new_better = self.base.answer(u_new, u_ref, rng, pair)
        self._memory[key] = said_new_better if new_id == key[0] else not said_new_better
        return said_new_better
