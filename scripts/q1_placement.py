"""Q1: placement accuracy vs questions asked, for every strategy and noise model.

Usage: python scripts/q1_placement.py [--tiny] [--workers N]
Writes runs/q1.jsonl (one row per configuration).
"""

from __future__ import annotations

import argparse
import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pairrank.conventions import DEFAULT_EPS
from pairrank.io import run_metadata, write_jsonl
from pairrank.metrics import list_tau, posterior_median_slot, tau_after_single_error
from pairrank.oracle import exact_slot_posterior
from pairrank.sim.noise import (
    BradleyTerryNoise,
    ConstantNoise,
    FirstAnswerWrong,
    NoiseModel,
    StickyNoise,
    calibrate_bt_temperature,
)
from pairrank.sim.session import build_list, simulate_insertions
from pairrank.state import InsertionState
from pairrank.strategies import BisectionInsertion, Strategy, VerifyInsertion, get_strategy

MASTER_SEED = 20261109
STRATEGIES = ["binary", "majority", "majority-neighbor", "bisection", "verify"]
EPS = [0.05, 0.1, 0.2, 0.3]
SIZES = [9, 19, 49, 99]
HEADLINE_N = 49
DELTAS = [0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01]
RHOS = [0.0, 0.5, 0.7, 0.9]
LIST_SIZE = 50
CALIBRATION_PAIRS = 400_000


@dataclass(frozen=True)
class Task:
    kind: str
    strategy: str
    noise: str  # "const", "bt", "sticky" or "first-wrong"
    n: int
    eps: float
    n_runs: int
    rho: float = 0.7
    delta: float = 0.1


def make_strategy(task: Task) -> Strategy:
    if task.strategy == "bisection":
        return BisectionInsertion(delta=task.delta)
    if task.strategy == "verify":
        return VerifyInsertion(delta=task.delta)
    return get_strategy(task.strategy)


def bt_temperature(eps: float) -> float:
    """T calibrated on differences of i.i.d. N(0, 1) utilities, the Q1 population."""
    rng = np.random.default_rng([MASTER_SEED, 7, int(round(eps * 1000))])
    deltas = rng.standard_normal(CALIBRATION_PAIRS) - rng.standard_normal(CALIBRATION_PAIRS)
    return calibrate_bt_temperature(eps, deltas)


def make_noise(task: Task) -> NoiseModel:
    if task.noise == "const":
        return ConstantNoise(task.eps)
    if task.noise == "first-wrong":
        return FirstAnswerWrong()
    bt = BradleyTerryNoise(bt_temperature(task.eps))
    return bt if task.noise == "bt" else StickyNoise(bt, task.rho)


def ci95(values: np.ndarray) -> float:
    return float(1.96 * values.std(ddof=1) / math.sqrt(values.shape[0]))


def insertion_row(task: Task, rng: np.random.Generator) -> dict[str, Any]:
    strategy = make_strategy(task)
    results = simulate_insertions(strategy, task.n, make_noise(task), task.n_runs, rng)
    errors = np.array([r.error for r in results], dtype=float)
    questions = np.array([r.n_questions for r in results], dtype=float)
    row: dict[str, Any] = {
        "mean_error": float(errors.mean()),
        "mean_error_ci95": ci95(errors),
        "exact_rate": float(np.mean(errors == 0)),
        "mean_questions": float(questions.mean()),
        "mean_questions_ci95": ci95(questions),
        "max_questions": int(questions.max()),
        "realized_error_rate": sum(r.n_wrong for r in results) / max(1.0, questions.sum()),
    }
    if isinstance(strategy, VerifyInsertion):
        row["contradiction_rate"] = float(
            np.mean(
                [
                    strategy.contradicted(
                        InsertionState(strategy=strategy.name, n=task.n, answers=r.answers)
                    )
                    for r in results
                ]
            )
        )
    return row


def list_row(task: Task, rng: np.random.Generator) -> dict[str, Any]:
    strategy = make_strategy(task)
    noise = make_noise(task)
    taus, questions, wrong = [], [], []
    for _ in range(task.n_runs):
        utilities = rng.standard_normal(task.n)
        built = build_list(strategy, utilities, noise, rng)
        taus.append(list_tau(built.order, utilities))
        questions.append(built.n_questions)
        wrong.append(built.n_wrong)
    tau_arr, q_arr = np.array(taus), np.array(questions, dtype=float)
    return {
        "mean_tau": float(tau_arr.mean()),
        "mean_tau_ci95": ci95(tau_arr),
        "mean_questions_per_list": float(q_arr.mean()),
        "realized_error_rate": float(sum(wrong) / q_arr.sum()),
    }


def per_question_rows(task: Task, rng: np.random.Generator) -> list[dict[str, Any]]:
    """Error after k questions: the slot a reader of the first k answers would pick.

    While a strategy is still asking, the estimate is the median of the posterior
    given those answers (eps_hat = 0.10). Once it has stopped, it's its final slot.
    """
    strategy = make_strategy(task)
    results = simulate_insertions(strategy, task.n, make_noise(task), task.n_runs, rng)
    k_max = 16
    totals = np.zeros(k_max + 1)
    for r in results:
        for k in range(k_max + 1):
            if k >= r.n_questions:
                estimate = r.slot
            else:
                post = exact_slot_posterior(r.answers[:k], task.n, DEFAULT_EPS)
                estimate = posterior_median_slot(post)
            totals[k] += abs(estimate - r.true_slot)
    mean_questions = float(np.mean([r.n_questions for r in results]))
    rows = []
    for k in range(k_max + 1):
        err = float(totals[k] / task.n_runs)
        rows.append(
            {
                "k": k,
                "mean_error": err,
                "tau_after_k": tau_after_single_error(err, task.n + 1),
                "mean_questions": mean_questions,
            }
        )
    return rows


def run_task(args: tuple[Task, np.random.SeedSequence]) -> list[dict[str, Any]]:
    task, seed = args
    rng = np.random.default_rng(seed)
    t0 = time.perf_counter()
    if task.kind == "list":
        rows = [list_row(task, rng)]
    elif task.kind == "per_question":
        rows = per_question_rows(task, rng)
    else:
        rows = [insertion_row(task, rng)]
    seconds = time.perf_counter() - t0
    return [{**asdict(task), **row, "seconds": seconds} for row in rows]


def build_tasks(scale: float) -> list[Task]:
    runs = max(20, int(10_000 * scale))
    list_runs = max(10, int(1_000 * scale))
    tasks = [
        Task("grid", s, m, n, eps, runs)
        for s in STRATEGIES
        for m in ("const", "bt", "sticky")
        for eps in EPS
        for n in SIZES
    ]
    tasks += [
        Task("delta_sweep", s, m, HEADLINE_N, eps, runs, delta=d)
        for s in ("bisection", "verify")
        for m in ("const", "bt")
        for eps in (0.05, 0.1, 0.2)
        for d in DELTAS
    ]
    tasks += [
        Task("sticky_sweep", s, "sticky", HEADLINE_N, 0.1, runs, rho=r)
        for s in STRATEGIES
        for r in RHOS
    ]
    tasks += [
        Task("list", s, m, LIST_SIZE, eps, list_runs)
        for s in STRATEGIES
        for m in ("const", "bt", "sticky")
        for eps in EPS
    ]
    tasks += [
        Task("per_question", s, "const", HEADLINE_N, 0.1, max(20, int(2_000 * scale)))
        for s in STRATEGIES
    ]
    tasks += [Task("adversarial", s, "first-wrong", HEADLINE_N, 0.0, runs) for s in STRATEGIES]
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    meta = run_metadata(MASTER_SEED)
    tasks = build_tasks(0.02 if args.tiny else 1.0)
    seeds = np.random.SeedSequence(MASTER_SEED).spawn(len(tasks))
    t0 = time.perf_counter()
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, batch in enumerate(pool.map(run_task, zip(tasks, seeds, strict=True), chunksize=4)):
            rows.extend({**row, **meta} for row in batch)
            if (i + 1) % 50 == 0:
                print(f"{i + 1}/{len(tasks)} tasks, {time.perf_counter() - t0:.0f} s", flush=True)
    out = Path("runs") / ("q1_tiny.jsonl" if args.tiny else "q1.jsonl")
    write_jsonl(out, rows)
    print(f"wrote {out}: {len(rows)} rows in {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
