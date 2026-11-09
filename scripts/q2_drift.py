"""Q2: how much 0-10 scores drift as a list grows.

Usage: python scripts/q2_drift.py [--tiny] [--workers N]
Writes runs/q2.jsonl.
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
from scipy.stats import norm

from pairrank.drift import (
    expected_churn,
    mean_abs_drift,
    score_history,
    true_scores,
    visible_churn,
)
from pairrank.io import run_metadata, write_jsonl
from pairrank.sim.noise import ConstantNoise
from pairrank.strategies import get_strategy

MASTER_SEED = 20261110
LIST_SIZE = 50
QS = [0.1, 0.25, 0.5]
AB = [(9, 24), (9, 49), (24, 49)]


@dataclass(frozen=True)
class Task:
    kind: str  # "law" or "mapping"
    mapping: str
    strategy: str
    eps: float
    users: int
    q: float = 0.0
    a: int = 9
    b: int = 49


def law_sd(q: float, a: int, b: int) -> float:
    return 10.0 * math.sqrt(q * (1.0 - q) * (1.0 / a - 1.0 / b))


def expected_mean_drift(a: int, b: int) -> float:
    """E|drift| for a uniform true quantile, normal approximation (E sqrt(q(1-q)) = pi/8)."""
    return 10.0 * math.sqrt(2.0 / math.pi) * (math.pi / 8.0) * math.sqrt(1.0 / a - 1.0 / b)


def run_task(args: tuple[Task, np.random.SeedSequence]) -> list[dict[str, Any]]:
    task, seed = args
    rng = np.random.default_rng(seed)
    strategy = get_strategy(task.strategy)
    noise = ConstantNoise(task.eps)
    t0 = time.perf_counter()
    if task.kind == "law":
        drifts = np.empty(task.users)
        for i in range(task.users):
            u = rng.standard_normal(task.b + 1)
            u[0] = float(norm.ppf(task.q))
            h = score_history(strategy, u, noise, rng, "percentile")  # type: ignore[arg-type]
            drifts[i] = h[task.b, 0] - h[task.a, 0]
        predicted = law_sd(task.q, task.a, task.b)
        sd = float(drifts.std(ddof=1))
        row = {"measured_sd": sd, "predicted_sd": predicted, "ratio": sd / predicted}
        return [{**asdict(task), **row, "seconds": time.perf_counter() - t0}]

    drift_curve = np.zeros(LIST_SIZE)
    churn = np.zeros(LIST_SIZE)
    drift_ten_fifty, abs_error = [], []
    for _ in range(task.users):
        u = rng.standard_normal(LIST_SIZE)
        h = score_history(strategy, u, noise, rng, task.mapping)  # type: ignore[arg-type]
        for b in range(10, LIST_SIZE):
            drift_curve[b] += mean_abs_drift(h, 9, b)
        for t in range(1, LIST_SIZE):
            churn[t] += visible_churn(h, t)
        drift_ten_fifty.append(mean_abs_drift(h, 9, 49))
        abs_error.append(float(np.mean(np.abs(h[-1] - true_scores(u)))))
    d, e = np.array(drift_ten_fifty), np.array(abs_error)
    row = {
        "mean_drift_10_to_50": float(d.mean()),
        "mean_drift_ci95": float(1.96 * d.std(ddof=1) / math.sqrt(task.users)),
        "visible_churn_50th": float(churn[49] / task.users),
        "accuracy_mean_abs_error": float(e.mean()),
        "accuracy_ci95": float(1.96 * e.std(ddof=1) / math.sqrt(task.users)),
        "drift_curve": (drift_curve / task.users).tolist(),
        "churn_curve": (churn / task.users).tolist(),
    }
    return [{**asdict(task), **row, "seconds": time.perf_counter() - t0}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    users = 100 if args.tiny else 2000
    tasks = [
        Task("law", "percentile", "binary", 0.0, users, q=q, a=a, b=b) for q in QS for a, b in AB
    ]
    tasks += [Task("mapping", m, "binary", 0.0, users) for m in ("percentile", "tiered")]
    tasks += [
        Task("mapping", m, s, 0.1, users)
        for m in ("percentile", "tiered")
        for s in ("binary", "bisection")
    ]
    meta = run_metadata(MASTER_SEED)
    seeds = np.random.SeedSequence(MASTER_SEED).spawn(len(tasks))
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for batch in pool.map(run_task, zip(tasks, seeds, strict=True)):
            rows.extend({**r, **meta} for r in batch)
    out = Path("runs") / ("q2_tiny.jsonl" if args.tiny else "q2.jsonl")
    write_jsonl(out, rows)
    print("law cells (q, a, b, measured SD, predicted SD, ratio):")
    for r in rows:
        if r["kind"] == "law":
            print(
                f"  {r['q']:.2f} {r['a']:>2} {r['b']:>2}  {r['measured_sd']:.3f}  "
                f"{r['predicted_sd']:.3f}  {r['ratio']:.3f}"
            )
    worst = max(abs(r["ratio"] - 1) for r in rows if r["kind"] == "law")
    print(f"worst law ratio deviation: {worst:.3f} (pass <= 0.10)")
    print(f"predicted mean drift 10 to 50: {expected_mean_drift(9, 49):.3f}")
    print(f"predicted churn at 49: {expected_churn(49):.3f}")
    for r in rows:
        if r["kind"] == "mapping":
            print(
                f"  {r['mapping']:>10} {r['strategy']:>9} eps={r['eps']:.1f}: drift "
                f"{r['mean_drift_10_to_50']:.3f} ± {r['mean_drift_ci95']:.3f}, churn "
                f"{r['visible_churn_50th']:.3f}, accuracy {r['accuracy_mean_abs_error']:.3f}"
            )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
