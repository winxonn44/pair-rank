"""Every SQL metric must equal its independent pandas version on the same simulated data.

Skips when Postgres or the backend extras are missing. In CI a missing database
is a failure, so this check can't silently stop running.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("django")

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import load_sim_to_pg as loader  # noqa: E402
import pandas_metrics  # noqa: E402

TEST_DATABASE = f"{loader.SIM_DATABASE}_test"
ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def rows() -> loader.Rows:
    return loader.generate(loader.TINY_USERS)


@pytest.fixture(scope="module")
def connection(rows: loader.Rows) -> Iterator[Any]:
    url = os.environ.get("DATABASE_URL", loader.DEFAULT_URL)
    try:
        psycopg.connect(loader.with_database(url, "postgres"), connect_timeout=3).close()
    except psycopg.OperationalError as error:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Postgres is not available: {error}")
    target = loader.rebuild_database(url, TEST_DATABASE)
    with psycopg.connect(target) as conn:
        loader.load(conn, rows)
        yield conn


@pytest.fixture(scope="module")
def sql_results(connection: Any) -> dict[str, pd.DataFrame]:
    return loader.run_queries(connection, ROOT / "sql" / "sim_metrics.sql")


@pytest.fixture(scope="module")
def frames(rows: loader.Rows) -> dict[str, pd.DataFrame]:
    return pandas_metrics.to_frames(rows, loader.COLUMNS)


def test_every_sql_metric_has_a_pandas_version() -> None:
    queries = loader.parse_named_queries(ROOT / "sql" / "sim_metrics.sql")
    assert set(queries) == set(pandas_metrics.METRICS)


@pytest.mark.parametrize("name", sorted(pandas_metrics.METRICS))
def test_sql_equals_pandas(
    name: str, sql_results: dict[str, pd.DataFrame], frames: dict[str, pd.DataFrame]
) -> None:
    result = sql_results[name]
    assert len(result) > 0
    assert pandas_metrics.compare(result, pandas_metrics.METRICS[name](frames)) <= 1e-9


def test_loaded_rows_are_all_in_the_database(connection: Any, rows: loader.Rows) -> None:
    for name, table in loader.TABLES.items():
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT count(*) FROM {table}")
            assert cursor.fetchone()[0] == len(rows[name]), table


def test_lists_are_contiguous_at_the_right_version(sql_results: dict[str, pd.DataFrame]) -> None:
    row = sql_results["list_integrity"].iloc[0]
    assert row["lists"] == loader.TINY_USERS * len(loader.STRATEGIES)
    assert (row["not_contiguous"], row["wrong_version"]) == (0, 0)


def test_binary_search_never_contradicts_itself(sql_results: dict[str, pd.DataFrame]) -> None:
    table = sql_results["contradiction_rate"].set_index("strategy")
    assert table.loc["binary", "contradicted"] == 0
    assert table.loc["bisection", "contradicted"] > 0


def test_analytics_queries_run_and_return_rows(connection: Any) -> None:
    results = loader.run_queries(connection, ROOT / "sql" / "analytics.sql")
    assert set(results) == {
        "funnel_by_day",
        "contradictions_by_user",
        "place_percentile_across_lists",
    }
    assert all(len(frame) > 0 for frame in results.values())
    quartiles = results["contradictions_by_user"]["quartile"]
    assert set(quartiles) == {1, 2, 3, 4}


def test_generate_is_reproducible() -> None:
    first = loader.generate(2)
    second = loader.generate(2)
    assert first == second
    assert first != loader.generate(2, master_seed=1)


def test_rebuild_refuses_any_other_database() -> None:
    with pytest.raises(ValueError, match="refusing"):
        loader.rebuild_database("postgres://x@127.0.0.1/x", "pairrank")


@pytest.mark.parametrize(
    ("column", "bad"),
    [("count", [1, 3]), ("rate", [0.5, 0.25 + 1e-6])],
)
def test_compare_catches_differences(column: str, bad: list[float]) -> None:
    good = pd.DataFrame({"count": [1, 2], "rate": [0.5, 0.25]})
    wrong = good.copy()
    wrong[column] = bad
    with pytest.raises(AssertionError):
        pandas_metrics.compare(wrong, good)


def test_compare_allows_rounding_noise() -> None:
    good = pd.DataFrame({"rate": [0.5, 0.25]})
    assert pandas_metrics.compare(good + 1e-12, good) <= 1e-9
