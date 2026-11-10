"""S4: load simulated sessions into Postgres, run the SQL metrics, check them with pandas.

Usage: python scripts/load_sim_to_pg.py [--tiny]
Needs Postgres (docker compose up -d --wait) and the backend extras. Rebuilds a
separate database, pairrank_sim, so it never touches the app's own data. Writes
runs/s4.jsonl (or runs/s4_tiny.jsonl).

Each simulated user starts with a correctly ordered list of 29 places and attempts
20 more, as in Q4, and may quit part-way through any question.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import pandas as pd
import psycopg

sys.path.insert(0, str(Path(__file__).parent))
import pandas_metrics  # noqa: E402

from pairrank.abtest import SESSION_INSERTIONS, START_SIZE  # noqa: E402
from pairrank.io import run_metadata, write_jsonl  # noqa: E402
from pairrank.sim.noise import ConstantNoise  # noqa: E402
from pairrank.sim.session import run_insertion  # noqa: E402
from pairrank.state import InsertionState  # noqa: E402
from pairrank.strategies import get_strategy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MASTER_SEED = 20261112
STRATEGIES = ["binary", "bisection", "majority", "majority-neighbor", "verify"]
EPS = 0.1
QUIT_HAZARD = 0.01  # chance of quitting at each question; an assumption, as in Q4
USERS = 500
TINY_USERS = 25
DEFAULT_URL = "postgres://pairrank:pairrank@127.0.0.1:5432/pairrank"
SIM_DATABASE = "pairrank_sim"
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)  # timestamps are synthetic and only give an order

COLUMNS: dict[str, tuple[str, ...]] = {
    "users": ("id", "username", "password", "is_superuser", "first_name", "last_name", "email")
    + ("is_staff", "is_active", "date_joined"),
    "places": ("id", "name", "city", "created_by_id"),
    "lists": ("id", "owner_id", "name", "version", "created_at"),
    "entries": ("list_id", "place_id", "position", "tier"),
    "insertions": ("id", "list_id", "place_id", "strategy", "tier", "state")
    + ("list_version_at_start", "n_questions", "final_position", "status")
    + ("started_at", "finished_at"),
    "comparisons": ("insertion_id", "question_index", "ref_place_id", "ref_position", "answer")
    + ("response_ms", "created_at"),
    "truth": ("insertion_id", "true_slot", "eps"),
}
TABLES = {
    "users": "auth_user",
    "places": "ranking_place",
    "lists": "ranking_ranklist",
    "entries": "ranking_listentry",
    "insertions": "ranking_insertion",
    "comparisons": "ranking_comparison",
    "truth": "sim_truth",
}
Rows = dict[str, list[tuple[Any, ...]]]


def generate(users_per_strategy: int, master_seed: int = MASTER_SEED) -> Rows:
    """Every row to load, with no database involved."""
    n_places = START_SIZE + SESSION_INSERTIONS
    rows: Rows = {name: [] for name in COLUMNS}
    rows["places"] = [(j + 1, f"Sim Place {j}", "Simulated", None) for j in range(n_places)]
    noise = ConstantNoise(EPS)
    strategy_seeds = np.random.SeedSequence(master_seed).spawn(len(STRATEGIES))
    user_id = insertion_id = 0

    for name, seed in zip(STRATEGIES, strategy_seeds, strict=True):
        strategy = get_strategy(name)
        for user_seed in seed.spawn(users_per_strategy):
            user_id += 1
            list_id = user_id
            when = EPOCH + timedelta(minutes=user_id)
            answers_seed, quit_seed = user_seed.spawn(2)
            rng = np.random.default_rng(answers_seed)
            quit_rng = np.random.default_rng(quit_seed)
            user_noise = noise.fresh()

            utilities = rng.standard_normal(n_places)
            order = np.argsort(-utilities[:START_SIZE], kind="stable").astype(np.int64).tolist()
            version = 0
            for k in range(SESSION_INSERTIONS):
                insertion_id += 1
                new_id = START_SIZE + k
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
                # The simulated user quits while looking at the first question that draws True.
                quits = quit_rng.random(result.n_questions) < QUIT_HAZARD
                quit_at = int(np.argmax(quits)) if quits.any() else None
                answers = result.answers if quit_at is None else result.answers[:quit_at]

                started = when + timedelta(hours=k)
                for index, (position, better) in enumerate(answers):
                    rows["comparisons"].append(
                        (
                            insertion_id,
                            index,
                            order[position] + 1,
                            position,
                            "better" if better else "worse",
                            None,
                            started + timedelta(seconds=2 * (index + 1)),
                        )
                    )
                state = InsertionState(strategy.name, result.n, tuple(answers), 0)
                finished = started + timedelta(seconds=2 * (len(answers) + 1))
                rows["insertions"].append(
                    (
                        insertion_id,
                        list_id,
                        new_id + 1,
                        strategy.name,
                        None,
                        state.to_json(),
                        version,
                        len(answers),
                        None if quit_at is not None else result.slot,
                        "done" if quit_at is None else "abandoned",
                        started,
                        finished,
                    )
                )
                rows["truth"].append((insertion_id, result.true_slot, EPS))
                if quit_at is None:
                    order.insert(result.slot, new_id)
                    version += 1

            rows["users"].append(
                (user_id, f"sim-{user_id}", "!", False, "", "", "", False, True, when)
            )
            rows["lists"].append((list_id, user_id, f"{strategy.name} user", version, when))
            rows["entries"].extend(
                (list_id, place + 1, position, None) for position, place in enumerate(order)
            )
    return rows


def with_database(url: str, database: str) -> str:
    return urlunsplit(urlsplit(url)._replace(path=f"/{database}"))


def rebuild_database(url: str, database: str) -> str:
    """Drop and recreate a simulation database, then apply the app's migrations."""
    if not database.startswith(SIM_DATABASE):
        raise ValueError(f"refusing to rebuild {database!r}: not a simulation database")
    with psycopg.connect(with_database(url, "postgres"), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{database}"')
    target = with_database(url, database)
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput", "-v", "0"],
        cwd=ROOT / "backend",
        env={**os.environ, "DATABASE_URL": target, "SECRET_KEY": "local-simulation-only"},
        check=True,
    )
    return target


def load(conn: psycopg.Connection, rows: Rows) -> None:
    """COPY every table in one transaction, so the deferred constraints check it all."""
    with conn.transaction(), conn.cursor() as cursor:
        cursor.execute(
            "CREATE TABLE sim_truth ("
            "insertion_id bigint PRIMARY KEY REFERENCES ranking_insertion (id),"
            "true_slot integer NOT NULL, eps double precision NOT NULL)"
        )
        for name in COLUMNS:
            columns = ", ".join(COLUMNS[name])
            with cursor.copy(f"COPY {TABLES[name]} ({columns}) FROM STDIN") as copy:
                for row in rows[name]:
                    copy.write_row(row)


def parse_named_queries(path: Path) -> dict[str, str]:
    """Split a .sql file on its `-- name: x` comments."""
    queries: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name:"):
            current = queries.setdefault(line.removeprefix("-- name:").strip(), [])
        elif current is not None:
            current.append(line)
    return {name: "\n".join(lines) for name, lines in queries.items()}


def run_queries(conn: psycopg.Connection, path: Path) -> dict[str, pd.DataFrame]:
    results = {}
    for name, query in parse_named_queries(path).items():
        with conn.cursor() as cursor:
            cursor.execute(query)
            assert cursor.description is not None
            columns = [column.name for column in cursor.description]
            data = [
                tuple(float(v) if isinstance(v, Decimal) else v for v in row)
                for row in cursor.fetchall()
            ]
        results[name] = pd.DataFrame(data, columns=columns)
    return results


def check_against_pandas(
    sql_results: Mapping[str, pd.DataFrame], rows: Rows, columns: Mapping[str, Sequence[str]]
) -> dict[str, float]:
    frames = pandas_metrics.to_frames(rows, columns)
    if set(sql_results) != set(pandas_metrics.METRICS):
        raise AssertionError("every SQL metric needs a pandas version, and the other way round")
    return {
        name: pandas_metrics.compare(sql_results[name], check(frames))
        for name, check in pandas_metrics.METRICS.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args()
    users = TINY_USERS if args.tiny else USERS
    database = f"{SIM_DATABASE}_tiny" if args.tiny else SIM_DATABASE
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)

    t0 = time.perf_counter()
    rows = generate(users)
    meta = run_metadata(MASTER_SEED)
    t1 = time.perf_counter()
    target = rebuild_database(url, database)
    with psycopg.connect(target) as conn:
        load(conn, rows)
        t2 = time.perf_counter()
        sql_results = run_queries(conn, ROOT / "sql" / "sim_metrics.sql")
        analytics = run_queries(conn, ROOT / "sql" / "analytics.sql")
    t3 = time.perf_counter()
    differences = check_against_pandas(sql_results, rows, COLUMNS)

    out: list[dict[str, Any]] = []
    for name, frame in sql_results.items():
        for record in frame.to_dict("records"):
            out.append({"metric": name, **record, **meta})
    for name, worst in differences.items():
        out.append(
            {
                "metric": "sql_vs_pandas",
                "query": name,
                "rows_compared": len(sql_results[name]),
                "max_abs_difference": worst,
                **meta,
            }
        )
    path = ROOT / "runs" / ("s4_tiny.jsonl" if args.tiny else "s4.jsonl")
    write_jsonl(path, out)

    counts = ", ".join(f"{name} {len(rows[name]):,}" for name in COLUMNS)
    print(f"loaded {counts}")
    print(f"generate {t1 - t0:.0f} s, load {t2 - t1:.0f} s, queries {t3 - t2:.1f} s")
    for name, worst in differences.items():
        print(f"  {name}: {len(sql_results[name])} rows match, max difference {worst:.2e}")
    print(f"analytics.sql: {', '.join(f'{k} {len(v)} rows' for k, v in analytics.items())}")
    for name in ("error_by_strategy", "questions_per_insertion", "contradiction_rate"):
        print(f"\n{name}\n{sql_results[name].to_string(index=False)}")
    print(f"\nabandonment_funnel\n{sql_results['abandonment_funnel'].to_string(index=False)}")
    print(f"\nper_user_ab\n{sql_results['per_user_ab'].to_string(index=False)}")
    print(f"\nlist_integrity\n{sql_results['list_integrity'].to_string(index=False)}")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
