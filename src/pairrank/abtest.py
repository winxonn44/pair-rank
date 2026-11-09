"""Q4: a simulated A/B test, with a power analysis checked by simulation.

A bank of simulated users is built once for each arm. An experiment then resamples
users from the banks, which is valid because simulated users are independent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy import stats as sps

from pairrank.sim.noise import NoiseModel
from pairrank.sim.session import run_insertion
from pairrank.strategies.base import Strategy

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

START_SIZE = 29  # an established user: entries already ranked, assumed correct
SESSION_INSERTIONS = 20  # list grows from 29 to 49, ending at Q1's headline size
N_AUDITS = 20
POCOCK_5_LOOKS = 0.0158  # nominal two-sided level for 5 equally spaced looks at overall 0.05


@dataclass(frozen=True)
class UserOutcome:
    errors: IntArray  # one per insertion
    questions: IntArray  # one per insertion
    audit_disagree: NDArray[np.bool_]  # one per audit question


def simulate_user(
    strategy: Strategy,
    noise: NoiseModel,
    rng: np.random.Generator,
    start_size: int = START_SIZE,
    insertions: int = SESSION_INSERTIONS,
    n_audits: int = N_AUDITS,
) -> UserOutcome:
    """One user's session. Errors compound: later places see earlier mistakes in the list."""
    user_noise = noise.fresh()
    utilities = rng.standard_normal(start_size + insertions)
    order = np.argsort(-utilities[:start_size], kind="stable").astype(np.int64).tolist()
    errors = np.zeros(insertions, dtype=np.int64)
    questions = np.zeros(insertions, dtype=np.int64)
    for k in range(insertions):
        new_id = start_size + k
        ids = np.asarray(order, dtype=np.int64)
        result = run_insertion(
            strategy,
            utilities[ids],
            float(utilities[new_id]),
            user_noise,
            rng,
            list_ids=ids,
            new_id=new_id,
        )
        order.insert(result.slot, new_id)
        errors[k] = result.error
        questions[k] = result.n_questions
    disagree = np.zeros(n_audits, dtype=np.bool_)
    for a in range(n_audits):
        i, j = sorted(rng.choice(len(order), size=2, replace=False).tolist())
        upper, lower = order[i], order[j]
        said_upper_better = user_noise.answer(
            float(utilities[upper]), float(utilities[lower]), rng, (upper, lower)
        )
        disagree[a] = not said_upper_better
    return UserOutcome(errors=errors, questions=questions, audit_disagree=disagree)


Z_ALPHA = float(sps.norm.ppf(0.975))
Z_POWER = float(sps.norm.ppf(0.80))


def n_per_arm(sigma: float, delta: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Users per arm for a two-sided two-sample test, normal approximation: 2(z+z)^2 s^2 / d^2."""
    if sigma <= 0 or delta <= 0:
        raise ValueError("sigma and delta must be positive")
    z = float(sps.norm.ppf(1.0 - alpha / 2.0)) + float(sps.norm.ppf(power))
    return math.ceil(2.0 * z * z * sigma * sigma / (delta * delta))


def welch_pvalue(a: FloatArray, b: FloatArray) -> FloatArray:
    """Two-sided Welch t-test along the last axis (one test per row)."""
    n_a, n_b = a.shape[-1], b.shape[-1]
    var_a, var_b = a.var(axis=-1, ddof=1) / n_a, b.var(axis=-1, ddof=1) / n_b
    se2 = var_a + var_b
    t = (a.mean(axis=-1) - b.mean(axis=-1)) / np.sqrt(se2)
    df = se2**2 / (var_a**2 / (n_a - 1) + var_b**2 / (n_b - 1))
    return np.asarray(2.0 * sps.t.sf(np.abs(t), df), dtype=np.float64)


def draw_user_means(
    control: IntArray,
    treatment: IntArray | None,
    fraction_treated: float,
    n_users: int,
    rng: np.random.Generator,
) -> FloatArray:
    """Per-user mean error for n_users resampled users.

    If `treatment` is given, each insertion independently goes through the treatment
    with probability `fraction_treated`, which scales the effect to f x (full effect).
    """
    picks = rng.integers(0, control.shape[0], n_users)
    rows = control[picks].astype(np.float64)
    if treatment is not None and fraction_treated > 0:
        treated_rows = treatment[rng.integers(0, treatment.shape[0], n_users)]
        mask = rng.random(rows.shape) < fraction_treated
        rows = np.where(mask, treated_rows, rows)
    return np.asarray(rows.mean(axis=1), dtype=np.float64)


def rejection_rate(
    control: IntArray,
    treatment: IntArray | None,
    fraction_treated: float,
    n_users: int,
    n_experiments: int,
    rng: np.random.Generator,
    alpha: float = 0.05,
) -> float:
    """Fraction of simulated experiments with p < alpha."""
    rejected = 0
    for _ in range(n_experiments):
        a = draw_user_means(control, None, 0.0, n_users, rng)
        b = draw_user_means(control, treatment, fraction_treated, n_users, rng)
        rejected += bool(welch_pvalue(a, b) < alpha)
    return rejected / n_experiments


def peeking_rate(
    control: IntArray,
    n_users: int,
    n_experiments: int,
    rng: np.random.Generator,
    looks: int = 5,
    alpha: float = 0.05,
) -> float:
    """A/A false-positive rate when testing at `looks` equally spaced interim analyses."""
    checkpoints = [n_users * (k + 1) // looks for k in range(looks)]
    rejected = 0
    for _ in range(n_experiments):
        a = draw_user_means(control, None, 0.0, n_users, rng)
        b = draw_user_means(control, None, 0.0, n_users, rng)
        if any(bool(welch_pvalue(a[:c], b[:c]) < alpha) for c in checkpoints):
            rejected += 1
    return rejected / n_experiments
