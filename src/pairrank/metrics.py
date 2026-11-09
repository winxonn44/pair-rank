"""Accuracy metrics. Conventions are in docs/conventions.md."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray


def _count_inversions(values: list[float]) -> tuple[list[float], int]:
    """Merge sort that also counts pairs out of order, O(N log N)."""
    if len(values) < 2:
        return values, 0
    middle = len(values) // 2
    left, inv_left = _count_inversions(values[:middle])
    right, inv_right = _count_inversions(values[middle:])
    merged: list[float] = []
    inversions = inv_left + inv_right
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            inversions += len(left) - i
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged, inversions


def kendall_tau(x: Sequence[float], y: Sequence[float]) -> float:
    """Kendall's tau for sequences with no ties: 1 - 4D / (N(N - 1)), in O(N log N)."""
    m = len(x)
    if m != len(y) or m < 2:
        raise ValueError("need two sequences of the same length >= 2")
    order = np.argsort(np.asarray(x), kind="stable")
    y_by_x = [float(y[int(i)]) for i in order]
    _, discordant = _count_inversions(y_by_x)
    return 1.0 - 4.0 * discordant / (m * (m - 1))


def list_tau(order: Sequence[int], utilities: NDArray[np.float64]) -> float:
    """Tau between a list (ids, best first) and the true utility order. 1 = perfect."""
    true_values = [float(utilities[i]) for i in order]
    positions = [-float(p) for p in range(len(order))]  # earlier in the list = ranked higher
    return kendall_tau(positions, true_values)


def tau_after_single_error(displacement: float, list_size: int) -> float:
    """Tau of an otherwise perfect list with one entry `displacement` positions off."""
    return 1.0 - 4.0 * displacement / (list_size * (list_size - 1))


def posterior_median_slot(post: NDArray[np.float64]) -> int:
    """The slot minimizing expected absolute error under a posterior."""
    return int(np.searchsorted(np.cumsum(post), 0.5))
