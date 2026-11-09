"""Q4: simulated A/B test of placement strategies, with a validated power analysis.

Usage: python scripts/q4_abtest.py [--tiny] [--workers N]
Writes runs/q4.jsonl. A user banks 20 insertions into a list growing from 29 to 49.
"""

from __future__ import annotations

import argparse
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from pairrank.abtest import (
    N_AUDITS,
    POCOCK_5_LOOKS,
    SESSION_INSERTIONS,
    draw_user_means,
    n_per_arm,
    peeking_rate,
    rejection_rate,
    simulate_user,
)
from pairrank.io import run_metadata, write_jsonl
from pairrank.sim.noise import ConstantNoise
from pairrank.strategies import get_strategy

MASTER_SEED = 20261111
EPS = 0.1
DELTAS = [0.25, 0.5, 1.0]
HAZARDS = [0.0, 0.005, 0.01, 0.02]
CHUNK = 500


def bank_chunk(args: tuple[str, str, int, np.random.SeedSequence]) -> tuple[np.ndarray, ...]:
    strategy_name, kind, users, seed = args
    rng = np.random.default_rng(seed)
    strategy = get_strategy(strategy_name)
    errors = np.zeros((users, SESSION_INSERTIONS), dtype=np.int64)
    questions = np.zeros((users, SESSION_INSERTIONS), dtype=np.int64)
    audits = np.zeros((users, N_AUDITS), dtype=np.bool_)
    for u in range(users):
        # Beta(2, 18) has a rare tail above 0.5, where an "error" stops being an error.
        eps = min(float(rng.beta(2.0, 18.0)), 0.49) if kind == "hetero" else EPS
        outcome = simulate_user(strategy, ConstantNoise(eps), rng)
        errors[u], questions[u], audits[u] = (
            outcome.errors,
            outcome.questions,
            outcome.audit_disagree,
        )
    return errors, questions, audits


def build_bank(
    pool: ProcessPoolExecutor, name: str, kind: str, users: int, seed: np.random.SeedSequence
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    chunks = [CHUNK] * (users // CHUNK) + ([users % CHUNK] if users % CHUNK else [])
    args = [(name, kind, c, s) for c, s in zip(chunks, seed.spawn(len(chunks)), strict=True)]
    parts = list(pool.map(bank_chunk, args))
    return (
        np.concatenate([p[0] for p in parts]),
        np.concatenate([p[1] for p in parts]),
        np.concatenate([p[2] for p in parts]),
    )


def mixed_sigma(
    control: np.ndarray, treatment: np.ndarray, f: float, rng: np.random.Generator
) -> float:
    """Pooled per-user SD of the two arms at treatment fraction f."""
    sample = 200_000
    var_a = draw_user_means(control, None, 0.0, sample, rng).var(ddof=1)
    var_b = draw_user_means(control, treatment, f, sample, rng).var(ddof=1)
    return math.sqrt((float(var_a) + float(var_b)) / 2.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    users = 1000 if args.tiny else 50_000
    experiments = 100 if args.tiny else 2000

    meta = run_metadata(MASTER_SEED)
    seeds = np.random.SeedSequence(MASTER_SEED).spawn(8)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        banks = {
            "binary": build_bank(pool, "binary", "homo", users, seeds[0]),
            "bisection": build_bank(pool, "bisection", "homo", users, seeds[1]),
            "verify": build_bank(pool, "verify", "homo", users, seeds[2]),
        }
        hetero = build_bank(pool, "binary", "hetero", users, seeds[3])
    bank_seconds = time.perf_counter() - t0
    print(f"banks built in {bank_seconds:.0f} s", flush=True)

    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(seeds[4])
    ctrl_e, ctrl_q, ctrl_a = banks["binary"]

    for name, (e, q, a) in banks.items():
        per_user = e.mean(axis=1)
        insertion_q = q.astype(np.float64)
        row: dict[str, Any] = {
            "kind": "arm",
            "strategy": name,
            "users": users,
            "mean_error": float(per_user.mean()),
            "mean_error_ci95": float(1.96 * per_user.std(ddof=1) / math.sqrt(users)),
            "user_sd": float(per_user.std(ddof=1)),
            "mean_questions": float(insertion_q.mean()),
            "audit_disagreement": float(a.mean()),
        }
        for h in HAZARDS:
            row[f"completion_h{h}"] = float(np.mean((1.0 - h) ** insertion_q))
        rows.append(row)
        print(row, flush=True)

    sigma_aa = float(ctrl_e.mean(axis=1).std(ddof=1))
    n_aa = n_per_arm(sigma_aa, 0.25)
    aa = rejection_rate(ctrl_e, None, 0.0, n_aa, experiments, rng)
    rows.append({"kind": "aa", "n_per_arm": n_aa, "experiments": experiments, "rate": aa})
    print(f"A/A at n={n_aa}: {aa:.4f} (pass [0.040, 0.060])", flush=True)

    looks5 = peeking_rate(ctrl_e, n_aa, experiments, rng, looks=5)
    pocock = peeking_rate(ctrl_e, n_aa, experiments, rng, looks=5, alpha=POCOCK_5_LOOKS)
    rows.append({"kind": "peeking", "n_per_arm": n_aa, "looks": 5, "alpha": 0.05, "rate": looks5})
    rows.append(
        {"kind": "peeking", "n_per_arm": n_aa, "looks": 5, "alpha": POCOCK_5_LOOKS, "rate": pocock}
    )
    print(f"peeking 5 looks: {looks5:.4f} (pass [0.127, 0.157]); pocock {pocock:.4f}", flush=True)

    for name in ("bisection", "verify"):
        treat_e = banks[name][0]
        full = float(ctrl_e.mean() - treat_e.mean())
        for delta in DELTAS:
            f = delta / full
            sigma = mixed_sigma(ctrl_e, treat_e, f, rng)
            n = n_per_arm(sigma, delta)
            power = rejection_rate(ctrl_e, treat_e, f, n, experiments, rng)
            curve = {}
            for mult in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5):
                nn = max(2, int(round(n * mult)))
                curve[str(mult)] = {
                    "n": nn,
                    "power": rejection_rate(ctrl_e, treat_e, f, nn, experiments // 2, rng),
                }
            rows.append(
                {
                    "kind": "power",
                    "treatment": name,
                    "delta": delta,
                    "full_effect": full,
                    "fraction_treated": f,
                    "sigma": sigma,
                    "n_per_arm": n,
                    "experiments": experiments,
                    "power": power,
                    "curve": curve,
                }
            )
            print(
                f"{name} delta={delta}: f={f:.3f} sigma={sigma:.3f} n={n} power={power:.4f} "
                "(pass [0.782, 0.818])",
                flush=True,
            )

    he, _, ha = hetero
    true_error = he.mean(axis=1)
    for m in (1, 5, 20):
        corr = float(np.corrcoef(ha[:, :m].mean(axis=1), true_error)[0, 1])
        rows.append({"kind": "proxy", "audits": m, "correlation": corr, "users": users})
        print(f"proxy audits={m}: corr with true error {corr:.3f}", flush=True)

    out = Path("runs") / ("q4_tiny.jsonl" if args.tiny else "q4.jsonl")
    write_jsonl(out, [{**r, **meta, "bank_seconds": bank_seconds} for r in rows])
    print(f"wrote {out} in {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
