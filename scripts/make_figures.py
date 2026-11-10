"""Every README figure and results table, from runs/*.jsonl. One command, no arguments.

Usage: python scripts/make_figures.py [--tiny]
Writes docs/figures/*.png and docs/tables/*.csv, and prints the hypothesis numbers.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

FIGURES = Path("docs/figures")
TABLES = Path("docs/tables")

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"

# Identity is carried by label and marker shape as well as color.
STYLE = {
    "binary": ("Binary insertion", "#2a78d6", "o"),
    "majority": ("Re-ask same pair", "#eb6834", "s"),
    "majority-neighbor": ("Re-ask neighbor pivot", "#1baf7a", "^"),
    "bisection": ("Bayesian bisection", "#eda100", "D"),
    "verify": ("Binary + check neighbors", "#e87ba4", "P"),
}

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.size": 11,
        "text.color": TEXT,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.edgecolor": GRID,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlelocation": "left",
        "axes.titleweight": "bold",
        "axes.titlesize": 13,
        "legend.frameon": False,
    }
)


def capacity_floor(n: int, eps: float) -> float:
    entropy = -eps * math.log2(eps) - (1 - eps) * math.log2(1 - eps)
    return math.log2(n + 1) / (1 - entropy)


def headline_figure(q1: pd.DataFrame, n: int = 49, eps: float = 0.1) -> None:
    grid = q1[(q1.kind == "grid") & (q1.noise == "const") & (q1.n == n) & (q1.eps == eps)]
    sweep = q1[(q1.kind == "delta_sweep") & (q1.noise == "const") & (q1.eps == eps)]
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=160)
    floor = capacity_floor(n, eps)
    ax.axvline(floor, color=MUTED, linewidth=1.2, linestyle=(0, (4, 3)), zorder=1)
    ax.annotate(
        f"information floor for\nnear-zero error:\n≈ {floor:.1f} questions",
        (floor, 0),
        xytext=(5, 150),
        textcoords="offset points",
        color=MUTED,
        fontsize=9.5,
    )
    for name in ("bisection", "verify"):
        label, color, marker = STYLE[name]
        curve = sweep[sweep.strategy == name].sort_values("mean_questions")
        ax.plot(
            curve.mean_questions,
            curve.mean_error,
            color=color,
            linewidth=2,
            marker=marker,
            markersize=6,
            markeredgecolor=SURFACE,
            markeredgewidth=1,
            label=f"{label} (varying stopping rule)",
            zorder=2,
        )
    offsets = {"binary": (8, 2), "majority": (8, -13), "majority-neighbor": (8, 3)}
    for name, offset in offsets.items():
        label, color, marker = STYLE[name]
        row = grid[grid.strategy == name].iloc[0]
        ax.scatter(
            row.mean_questions,
            row.mean_error,
            s=90,
            color=color,
            marker=marker,
            edgecolor=SURFACE,
            linewidth=1.5,
            label=label,
            zorder=3,
        )
        ax.annotate(
            label,
            (row.mean_questions, row.mean_error),
            xytext=offset,
            textcoords="offset points",
            color=TEXT,
            fontsize=9.5,
        )
    ax.set_title(f"Fewer mistakes cost more questions (list of {n}, {eps:.0%} wrong answers)")
    ax.set_xlabel("Average questions asked per restaurant")
    ax.set_ylabel("Average placement error (positions)")
    ax.set_ylim(bottom=0)
    ax.set_xlim(0, 16.5)
    ax.legend(loc="lower left", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(FIGURES / "q1_error_vs_questions.png")
    plt.close(fig)


def per_question_figure(q1: pd.DataFrame) -> None:
    pq = q1[q1.kind == "per_question"]
    fig, ax = plt.subplots(figsize=(8.4, 4.8), dpi=160)
    for name in ("binary", "majority", "bisection", "verify"):
        label, color, marker = STYLE[name]
        curve = pq[pq.strategy == name].sort_values("k")
        ax.plot(
            curve.k,
            curve.mean_error,
            color=color,
            linewidth=2,
            marker=marker,
            markersize=5,
            markevery=2,
            markeredgecolor=SURFACE,
            label=label,
        )
    ax.set_title("Accuracy after each extra question (list of 49, 10% wrong answers)")
    ax.set_xlabel("Questions asked so far")
    ax.set_ylabel("Average placement error (positions)")
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(FIGURES / "q1_error_per_question.png")
    plt.close(fig)


def tables(q1: pd.DataFrame) -> pd.DataFrame:
    grid = q1[q1.kind == "grid"]
    summary = grid.pivot_table(
        index=["noise", "eps", "n", "strategy"],
        values=["mean_error", "mean_error_ci95", "exact_rate", "mean_questions"],
    ).round(3)
    summary.to_csv(TABLES / "q1_grid.csv")
    lists = q1[q1.kind == "list"].pivot_table(
        index=["noise", "eps"], columns="strategy", values="mean_tau"
    )
    lists.round(4).to_csv(TABLES / "q1_list_tau.csv")
    return grid


def interp_questions_at_error(curve: pd.DataFrame, target_error: float) -> float:
    c = curve.sort_values("mean_error")
    return float(np.interp(target_error, c.mean_error, c.mean_questions))


def hypotheses(q1: pd.DataFrame, grid: pd.DataFrame) -> None:
    pd.set_option("display.width", 200, "display.max_columns", 30)

    def cell(strategy: str, noise: str = "const", n: int = 49, eps: float = 0.1) -> pd.Series:
        selected = grid[
            (grid.strategy == strategy) & (grid.noise == noise) & (grid.n == n) & (grid.eps == eps)
        ]
        return selected.iloc[0]

    print("\n== headline: n=49, eps=0.1, const ==")
    cols = ["strategy", "mean_error", "mean_error_ci95", "exact_rate", "mean_questions"]
    h = grid[(grid.noise == "const") & (grid.n == 49) & (grid.eps == 0.1)]
    print(h[cols].to_string(index=False))

    print("\n== H1 ratio exact-ish sim / first order, binary const ==")
    for eps in (0.05, 0.1, 0.2, 0.3):
        print(
            eps,
            [
                round(float(cell("binary", n=n, eps=eps).mean_error) / (eps * (n + 1) / 2), 3)
                for n in (9, 19, 49, 99)
            ],
        )

    print("\n== H2 binary error, const vs bt at same average eps ==")
    for eps in (0.05, 0.1, 0.2, 0.3):
        c, b = cell("binary", eps=eps), cell("binary", "bt", eps=eps)
        print(
            f"eps={eps}: const {c.mean_error:.3f} bt {b.mean_error:.3f} "
            f"ratio {c.mean_error / b.mean_error:.2f}; "
            f"realized error during search: const {c.realized_error_rate:.3f} "
            f"bt {b.realized_error_rate:.3f}"
        )

    print("\n== H3 verify vs binary, n=49, by noise ==")
    for noise in ("const", "bt", "sticky"):
        for eps in (0.05, 0.1, 0.2, 0.3):
            b, v = cell("binary", noise, eps=eps), cell("verify", noise, eps=eps)
            print(
                f"{noise} eps={eps}: binary {b.mean_error:.3f}/{b.mean_questions:.2f}q "
                f"verify {v.mean_error:.3f}/{v.mean_questions:.2f}q "
                f"error cut {1 - v.mean_error / b.mean_error:.1%} "
                f"extra {v.mean_questions - b.mean_questions:.2f}q "
                f"contradiction {v.contradiction_rate:.3f}"
            )

    print("\n== H4 bisection vs majority at equal error ==")
    sweep = q1[(q1.kind == "delta_sweep") & (q1.strategy == "bisection")]
    for noise in ("const", "bt"):
        for eps in (0.05, 0.1, 0.2):
            m = cell("majority", noise, eps=eps)
            curve = sweep[(sweep.noise == noise) & (sweep.eps == eps)]
            low, high = curve.mean_error.min(), curve.mean_error.max()
            q = interp_questions_at_error(curve, m.mean_error)
            inside = low <= m.mean_error <= high
            print(
                f"{noise} eps={eps}: majority {m.mean_error:.3f} at {m.mean_questions:.2f}q; "
                f"bisection at that error {q:.2f}q; fewer {1 - q / m.mean_questions:.1%} "
                f"(in sweep range: {inside}, range {low:.3f}-{high:.3f})"
            )
    print(
        sweep[(sweep.noise == "const") & (sweep.eps == 0.1)][
            ["delta", "mean_error", "mean_questions", "exact_rate"]
        ].to_string(index=False)
    )

    print("\n== H6 sticky sweep, n=49, eps=0.1 ==")
    sticky = q1[q1.kind == "sticky_sweep"].pivot_table(
        index="rho", columns="strategy", values="mean_error"
    )
    print(sticky.round(3).to_string())
    print(
        q1[q1.kind == "sticky_sweep"]
        .pivot_table(index="rho", columns="strategy", values="mean_questions")
        .round(2)
        .to_string()
    )

    print("\n== adversarial first-answer-wrong, n=49 ==")
    print(
        q1[q1.kind == "adversarial"][
            ["strategy", "mean_error", "mean_questions", "exact_rate", "contradiction_rate"]
        ].to_string(index=False)
    )

    print("\n== whole lists, N=50, mean tau ==")
    print(
        q1[q1.kind == "list"]
        .pivot_table(index=["noise", "eps"], columns="strategy", values="mean_tau")
        .round(4)
        .to_string()
    )
    print(
        q1[q1.kind == "list"]
        .pivot_table(index=["noise", "eps"], columns="strategy", values="mean_questions_per_list")
        .round(0)
        .to_string()
    )

    meta = q1.iloc[0]
    print(
        f"\nrun: commit {meta.git_commit} dirty={meta.git_dirty} power={meta.power} "
        f"numpy {meta.numpy}; total task-seconds {q1.seconds.sum():.0f}"
    )


def q2_outputs(path: Path) -> None:
    q2 = pd.read_json(path, lines=True, precise_float=True)
    maps = q2[(q2.kind == "mapping") & (q2.strategy == "binary") & (q2.eps == 0.0)]
    fig, ax = plt.subplots(figsize=(8.4, 4.8), dpi=160)
    xs = np.arange(10, 50)
    theory = (
        10.0
        * math.sqrt(2.0 / math.pi)
        * (math.pi / 8.0)
        * np.sqrt(1.0 / 9.0 - 1.0 / np.maximum(xs, 10))
    )
    ax.plot(
        xs + 1,
        theory,
        color=MUTED,
        linewidth=1.5,
        linestyle=(0, (4, 3)),
        label="Percentile, predicted in advance",
        zorder=1,
    )
    styles = {
        "percentile": ("Percentile mapping, simulated", "#2a78d6", "o"),
        "tiered": ("Three tiers, simulated", "#eb6834", "s"),
    }
    for name, (label, color, marker) in styles.items():
        curve = np.array(maps[maps.mapping == name].iloc[0].drift_curve)[10:]
        ax.plot(
            xs + 1,
            curve,
            color=color,
            linewidth=2,
            marker=marker,
            markersize=6,
            markevery=5,
            markeredgecolor=SURFACE,
            label=label,
            zorder=2,
        )
    ax.set_title("Scores drift even when answers are perfectly consistent")
    ax.set_xlabel("Number of restaurants in the list")
    ax.set_ylabel("Average score change since the 10th entry (points)")
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(FIGURES / "q2_drift.png")
    plt.close(fig)
    table = q2[q2.kind == "mapping"][
        [
            "mapping",
            "strategy",
            "eps",
            "mean_drift_10_to_50",
            "mean_drift_ci95",
            "visible_churn_50th",
            "accuracy_mean_abs_error",
        ]
    ]
    table.round(3).to_csv(TABLES / "q2_mappings.csv", index=False)


def q4_outputs(path: Path) -> None:
    q4 = pd.read_json(path, lines=True, precise_float=True)
    power = q4[(q4.kind == "power") & (q4.treatment == "bisection") & (q4.delta == 0.25)].iloc[0]
    points = pd.DataFrame(power.curve).T.sort_values("n")
    sigma, delta = float(power.sigma), float(power.delta)
    ns = np.linspace(max(2, points.n.min() * 0.8), points.n.max() * 1.1, 200)
    z_alpha = 1.959964
    from scipy.stats import norm

    predicted = norm.cdf(delta / (sigma * np.sqrt(2.0 / ns)) - z_alpha)
    fig, ax = plt.subplots(figsize=(8.4, 4.8), dpi=160)
    ax.plot(
        ns,
        predicted,
        color=MUTED,
        linewidth=1.5,
        linestyle=(0, (4, 3)),
        label="Power formula",
        zorder=1,
    )
    ax.scatter(
        points.n,
        points.power,
        s=70,
        color="#2a78d6",
        edgecolor=SURFACE,
        linewidth=1.5,
        label="Simulated experiments",
        zorder=2,
    )
    n_star = int(power.n_per_arm)
    ax.axvline(n_star, color=GRID, linewidth=1.2, zorder=0)
    ax.annotate(
        f"{n_star} users per arm",
        (n_star, 0.32),
        xytext=(6, 0),
        textcoords="offset points",
        color=MUTED,
        fontsize=9.5,
    )
    ax.set_title(f"How many users to detect a {delta:g}-position improvement?")
    ax.set_xlabel("Users per arm")
    ax.set_ylabel("Chance the test detects it")
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right", fontsize=9.5)
    fig.tight_layout()
    fig.savefig(FIGURES / "q4_power.png")
    plt.close(fig)
    q4[q4.kind == "arm"].drop(columns=["curve", "timestamp_utc"], errors="ignore").dropna(
        axis=1, how="all"
    ).round(4).to_csv(TABLES / "q4_arms.csv", index=False)


def s4_outputs(path: Path) -> None:
    s4 = pd.read_json(path, lines=True, precise_float=True)

    def metric(name: str, columns: list[str]) -> pd.DataFrame:
        return s4.loc[s4.metric == name, columns]

    summary = (
        metric("error_by_strategy", ["strategy", "mean_error", "exact_rate"])
        .merge(metric("questions_per_insertion", ["strategy", "mean_questions", "p95_questions"]))
        .merge(metric("contradiction_rate", ["strategy", "contradiction_rate"]))
        .merge(metric("abandonment_funnel", ["strategy", "completion_rate"]))
    )
    summary.round(4).to_csv(TABLES / "s4_strategies.csv", index=False)
    checks = metric("sql_vs_pandas", ["query", "rows_compared", "max_abs_difference"])
    checks.to_csv(TABLES / "s4_sql_vs_pandas.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    q1 = pd.read_json(
        Path("runs") / ("q1_tiny.jsonl" if args.tiny else "q1.jsonl"),
        lines=True,
        precise_float=True,
    )
    grid = tables(q1)
    headline_figure(q1)
    per_question_figure(q1)
    hypotheses(q1, grid)
    suffix = "_tiny" if args.tiny else ""
    q2_outputs(Path("runs") / f"q2{suffix}.jsonl")
    q4_outputs(Path("runs") / f"q4{suffix}.jsonl")
    s4_outputs(Path("runs") / f"s4{suffix}.jsonl")


if __name__ == "__main__":
    main()
