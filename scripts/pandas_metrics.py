"""Independent pandas versions of every query in sql/sim_metrics.sql.

SQL is the primary implementation. These work from the rows the simulator generated
in memory, never from the database, so a lost row or a bad join shows up as a mismatch.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats

Frames = Mapping[str, pd.DataFrame]


def to_frames(
    rows: Mapping[str, Sequence[tuple[object, ...]]], columns: Mapping[str, Sequence[str]]
) -> dict[str, pd.DataFrame]:
    return {name: pd.DataFrame(rows[name], columns=list(columns[name])) for name in rows}


def _percentile_disc(p: float) -> Callable[[pd.Series], int]:
    """Postgres's percentile_disc: the value at row ceil(p * N) of the sorted data."""

    def compute(values: pd.Series) -> int:
        return int(np.sort(values.to_numpy())[math.ceil(p * len(values)) - 1])

    return compute


def _done_with_error(frames: Frames) -> pd.DataFrame:
    ins = frames["insertions"]
    done = ins[ins["status"] == "done"].merge(
        frames["truth"], left_on="id", right_on="insertion_id", how="inner", validate="one_to_one"
    )
    return done.assign(error=(done["final_position"].astype("int64") - done["true_slot"]).abs())


def questions_per_insertion(frames: Frames) -> pd.DataFrame:
    ins = frames["insertions"]
    grouped = ins[ins["status"] == "done"].groupby("strategy")["n_questions"]
    return pd.DataFrame(
        {
            "insertions": grouped.size(),
            "total_questions": grouped.sum(),
            "mean_questions": grouped.mean(),
            "sd_questions": grouped.std(ddof=1),
            "p50_questions": grouped.apply(_percentile_disc(0.5)),
            "p95_questions": grouped.apply(_percentile_disc(0.95)),
            "max_questions": grouped.max(),
        }
    ).reset_index()


def error_by_strategy(frames: Frames) -> pd.DataFrame:
    done = _done_with_error(frames)
    grouped = done.groupby("strategy")["error"]
    return pd.DataFrame(
        {
            "insertions": grouped.size(),
            "total_error": grouped.sum(),
            "mean_error": grouped.mean(),
            "exact_rate": grouped.apply(lambda e: (e == 0).mean()),
            "within_one_rate": grouped.apply(lambda e: (e <= 1).mean()),
            "p95_error": grouped.apply(_percentile_disc(0.95)),
            "max_error": grouped.max(),
        }
    ).reset_index()


def contradiction_rate(frames: Frames) -> pd.DataFrame:
    comp = frames["comparisons"]
    lowest = comp[comp["answer"] == "better"].groupby("insertion_id")["ref_position"].min()
    highest = comp[comp["answer"] == "worse"].groupby("insertion_id")["ref_position"].max()
    ins = frames["insertions"]
    done = ins[(ins["status"] == "done") & ins["id"].isin(comp["insertion_id"])].copy()
    # A missing bound compares as False, as NULL does in the SQL filter.
    done["contradicted"] = done["id"].map(highest) >= done["id"].map(lowest)
    grouped = done.groupby("strategy")["contradicted"]
    return pd.DataFrame(
        {
            "insertions": grouped.size(),
            "contradicted": grouped.sum().astype("int64"),
            "contradiction_rate": grouped.mean(),
        }
    ).reset_index()


def abandonment_funnel(frames: Frames) -> pd.DataFrame:
    ins = frames["insertions"]
    grouped = ins.groupby("strategy")
    return pd.DataFrame(
        {
            "started": grouped.size(),
            "answered_first": grouped["n_questions"].apply(lambda q: int((q > 0).sum())),
            "done": grouped["status"].apply(lambda s: int((s == "done").sum())),
            "abandoned": grouped["status"].apply(lambda s: int((s == "abandoned").sum())),
            "completion_rate": grouped["status"].apply(lambda s: (s == "done").mean()),
        }
    ).reset_index()


def dropoff_by_question(frames: Frames) -> pd.DataFrame:
    ins = frames["insertions"]
    records = []
    for strategy, n_questions, status in zip(
        ins["strategy"], ins["n_questions"], ins["status"], strict=True
    ):
        quit_session = status == "abandoned"
        last = n_questions if quit_session else n_questions - 1
        records.extend((strategy, q, quit_session and q == n_questions) for q in range(last + 1))
    asked = pd.DataFrame(records, columns=["strategy", "q", "quit"])
    out = (
        asked.groupby(["strategy", "q"])["quit"]
        .agg(asked="size", quit_here="sum")
        .reset_index()
        .sort_values(["strategy", "q"], ignore_index=True)
    )
    out["quit_here"] = out["quit_here"].astype("int64")
    out["hazard"] = out["quit_here"] / out["asked"]
    out["cumulative_quits"] = out.groupby("strategy")["quit_here"].cumsum()
    return out


def error_by_session_position(frames: Frames) -> pd.DataFrame:
    ins = frames["insertions"].sort_values("id")
    position = ins.groupby("list_id").cumcount() + 1
    done = _done_with_error(frames)
    done["session_position"] = done["id"].map(pd.Series(position.to_numpy(), index=ins["id"]))
    return (
        done.groupby(["strategy", "session_position"])["error"]
        .agg(insertions="size", mean_error="mean")
        .reset_index()
    )


def per_user_ab(frames: Frames) -> pd.DataFrame:
    done = _done_with_error(frames)
    means = done.groupby(["strategy", "list_id"])["error"].mean().reset_index()
    control = means.loc[means["strategy"] == "binary", "error"].to_numpy()
    rows = []
    for strategy, group in means[means["strategy"] != "binary"].groupby("strategy"):
        treated = group["error"].to_numpy()
        se = math.sqrt(treated.var(ddof=1) / len(treated) + control.var(ddof=1) / len(control))
        rows.append(
            {
                "strategy": strategy,
                "users": len(treated),
                "control_mean_error": control.mean(),
                "treatment_mean_error": treated.mean(),
                "difference": treated.mean() - control.mean(),
                "standard_error": se,
                "welch_t": float(stats.ttest_ind(treated, control, equal_var=False).statistic),
            }
        )
    return pd.DataFrame(rows).sort_values("strategy", ignore_index=True)


def list_integrity(frames: Frames) -> pd.DataFrame:
    entries = frames["entries"].groupby("list_id")["position"]
    ins = frames["insertions"]
    done = ins[ins["status"] == "done"].groupby("list_id").size()
    summary = (
        frames["lists"]
        .set_index("id")
        .join(
            pd.DataFrame(
                {
                    "entries": entries.size(),
                    "first_position": entries.min(),
                    "last_position": entries.max(),
                    "distinct_positions": entries.nunique(),
                }
            ),
            how="inner",
        )
    )
    summary["done"] = done.reindex(summary.index, fill_value=0)
    broken = (
        (summary["first_position"] != 0)
        | (summary["last_position"] != summary["entries"] - 1)
        | (summary["distinct_positions"] != summary["entries"])
    )
    return pd.DataFrame(
        {
            "lists": [len(summary)],
            "not_contiguous": [int(broken.sum())],
            "wrong_version": [int((summary["version"] != summary["done"]).sum())],
        }
    )


METRICS: dict[str, Callable[[Frames], pd.DataFrame]] = {
    "questions_per_insertion": questions_per_insertion,
    "error_by_strategy": error_by_strategy,
    "contradiction_rate": contradiction_rate,
    "abandonment_funnel": abandonment_funnel,
    "dropoff_by_question": dropoff_by_question,
    "error_by_session_position": error_by_session_position,
    "per_user_ab": per_user_ab,
    "list_integrity": list_integrity,
}


def compare(sql: pd.DataFrame, expected: pd.DataFrame, tolerance: float = 1e-9) -> float:
    """Raise if two results differ: exact for integers and text, `tolerance` for floats.

    Returns the largest absolute difference found in a float column.
    """
    if list(sql.columns) != list(expected.columns):
        raise AssertionError(f"columns differ: {list(sql.columns)} vs {list(expected.columns)}")
    if len(sql) != len(expected):
        raise AssertionError(f"row counts differ: {len(sql)} vs {len(expected)}")
    worst = 0.0
    for column in sql.columns:
        a, b = sql[column].reset_index(drop=True), expected[column].reset_index(drop=True)
        if pd.api.types.is_float_dtype(a) or pd.api.types.is_float_dtype(b):
            difference = (a.astype("float64") - b.astype("float64")).abs()
            if difference.isna().any():
                raise AssertionError(f"{column}: missing values")
            worst = max(worst, float(difference.max()))
            if worst > tolerance:
                raise AssertionError(f"{column}: differs by {worst}")
        elif not (a.astype(str) == b.astype(str)).all():
            raise AssertionError(f"{column}: values differ")
    return worst
