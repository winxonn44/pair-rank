"""Query counts must not grow with the list. A missing select_related would show up here.

Counts include the session and user lookups. Transaction control (BEGIN, SAVEPOINT
and so on) is left out, because the test wrapper changes how much of it there is.
"""

from collections.abc import Callable
from functools import partial
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.response import Response

from ranking.tests.helpers import answer, fill_list, new_guest_list, start

pytestmark = pytest.mark.django_db

TRANSACTION_CONTROL = ("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE SAVEPOINT")
MAX_ANSWER_QUERIES = 6
MAX_FINISHING_ANSWER_QUERIES = 10
MAX_START_QUERIES = 10
MAX_GET_LIST_QUERIES = 4


@pytest.fixture(autouse=True)
def binary_strategy(settings: Any) -> None:
    settings.PAIRRANK_DEFAULT_STRATEGY = "binary"


def count_queries(request: Callable[[], Response]) -> int:
    with CaptureQueriesContext(connection) as captured:
        response = request()
    assert response.status_code < 300
    return sum(not q["sql"].startswith(TRANSACTION_CONTROL) for q in captured.captured_queries)


@pytest.mark.parametrize("n", [10, 50])
def test_get_list_is_bounded(n: int) -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, n)
    assert count_queries(lambda: client.get(f"/api/lists/{list_id}/")) <= MAX_GET_LIST_QUERIES


def run_one_insertion(n: int) -> tuple[int, list[int], int]:
    client, list_id = new_guest_list()
    fill_list(list_id, n)
    with CaptureQueriesContext(connection) as captured:
        response = start(client, list_id, f"New Spot {list_id}")
    assert response.status_code == 201
    start_queries = sum(
        not q["sql"].startswith(TRANSACTION_CONTROL) for q in captured.captured_queries
    )
    insertion_id = response.data["insertion_id"]
    index = 0
    counts = []
    while True:
        counts.append(count_queries(partial(answer, client, insertion_id, index, "worse")))
        index += 1
        if index > n:
            raise AssertionError("binary insertion should have finished")
        if client.get(f"/api/lists/{list_id}/").data["version"] == 1:
            break
    return start_queries, counts[:-1], counts[-1]


@pytest.mark.parametrize("n", [10, 50])
def test_answer_and_start_are_bounded(n: int) -> None:
    start_queries, question_counts, finishing = run_one_insertion(n)
    assert start_queries <= MAX_START_QUERIES
    assert question_counts, "expected at least one question before the last"
    assert max(question_counts) <= MAX_ANSWER_QUERIES
    assert finishing <= MAX_FINISHING_ANSWER_QUERIES


def test_counts_do_not_depend_on_list_size() -> None:
    small = run_one_insertion(10)
    large = run_one_insertion(50)
    assert small[0] == large[0]
    assert max(small[1]) == max(large[1])
    assert small[2] == large[2]
