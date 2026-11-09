"""S0: simulated binary insertion vs the exact enumeration oracle, on the Q1 grid.

Usage: python scripts/s0_oracle_check.py [--tiny]
Writes runs/s0_oracle.jsonl and prints a table.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np

from pairrank.io import run_metadata, write_jsonl
from pairrank.oracle import enumerate_binary_insertion, mean_abs_error, signed_error_pmf
from pairrank.sim.noise import ConstantNoise
from pairrank.sim.session import simulate_insertions
from pairrank.stats import chi2_against_pmf
from pairrank.strategies import BinaryInsertion

MASTER_SEED = 20261106
SIZES = [9, 19, 49, 99]
EPS = [0.05, 0.1, 0.2, 0.3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true", help="200 insertions per cell")
    args = parser.parse_args()
    n_insertions = 200 if args.tiny else 10_000

    meta = run_metadata(MASTER_SEED)
    cells = [(n, eps) for n in SIZES for eps in EPS]
    streams = np.random.SeedSequence(MASTER_SEED).spawn(len(cells))
    rows = []
    print(f"{'n':>4} {'eps':>5} {'exact':>7} {'sim':>7} {'z':>6} {'chi2 p':>8} {'1st-ord':>8}")
    for (n, eps), ss in zip(cells, streams, strict=True):
        t0 = time.perf_counter()
        results = simulate_insertions(
            BinaryInsertion(), n, ConstantNoise(eps), n_insertions, np.random.default_rng(ss)
        )
        errors = np.array([r.error for r in results], dtype=float)
        p = enumerate_binary_insertion(n, eps)
        exact = mean_abs_error(p)
        se = float(errors.std(ddof=1) / math.sqrt(len(errors)))
        chi2, dof, pvalue = chi2_against_pmf(
            [r.slot - r.true_slot for r in results], signed_error_pmf(p)
        )
        row = {
            "check": "s0_binary_vs_oracle",
            "strategy": "binary",
            "noise": "const",
            "n": n,
            "eps": eps,
            "n_insertions": n_insertions,
            "exact_mean_abs_error": exact,
            "first_order_prediction": eps * (n + 1) / 2,
            "sim_mean_abs_error": float(errors.mean()),
            "sim_se": se,
            "z": (float(errors.mean()) - exact) / se if se > 0 else 0.0,
            "sim_exact_placement_rate": float(np.mean(errors == 0)),
            "sim_mean_questions": float(np.mean([r.n_questions for r in results])),
            "chi2": chi2,
            "chi2_dof": dof,
            "chi2_p": pvalue,
            "seconds": time.perf_counter() - t0,
            **meta,
        }
        rows.append(row)
        print(
            f"{n:>4} {eps:>5.2f} {exact:>7.3f} {row['sim_mean_abs_error']:>7.3f} "
            f"{row['z']:>6.2f} {pvalue:>8.3f} {row['first_order_prediction']:>8.3f}"
        )
    out = Path("runs") / ("s0_oracle_tiny.jsonl" if args.tiny else "s0_oracle.jsonl")
    write_jsonl(out, rows)
    worst = max(abs(r["z"]) for r in rows)
    min_p = min(r["chi2_p"] for r in rows)
    print(f"wrote {out}; max |z| = {worst:.2f} (pass < 3); min chi2 p = {min_p:.4f} (pass > 0.001)")


if __name__ == "__main__":
    main()
