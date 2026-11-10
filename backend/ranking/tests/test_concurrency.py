"""Two tabs racing on one list, over real connections with real commits."""

import threading
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.response import Response
from rest_framework.test import APIClient

from ranking.models import Insertion, RankList
from ranking.tests.helpers import answer, fill_list, positions, start

ROUNDS = 25


def race_final_answers(
    clients: list[APIClient], insertion_ids: list[int]
) -> list[Response | Exception]:
    """Send one final answer per client, as close to simultaneously as possible."""
    barrier = threading.Barrier(len(clients))
    results: list[Response | Exception] = [RuntimeError("did not run")] * len(clients)

    def worker(slot: int) -> None:
        try:
            barrier.wait(timeout=10)
            results[slot] = answer(clients[slot], insertion_ids[slot], 0, "better")
        except Exception as exc:  # reported by the assertion in the test
            results[slot] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(clients))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


@pytest.mark.django_db(transaction=True)
def test_racing_insertions_have_one_winner(settings: Any) -> None:
    settings.PAIRRANK_DEFAULT_STRATEGY = "binary"
    owner = get_user_model().objects.create_user(username="guest-race")
    tabs = [APIClient(), APIClient()]
    for tab in tabs:
        tab.force_login(owner)

    for round_number in range(ROUNDS):
        ranked = RankList.objects.create(owner=owner, name=f"race {round_number}")
        fill_list(ranked.pk, 1, prefix=f"race{round_number}")
        insertion_ids = [
            start(tab, ranked.pk, f"race {round_number} tab {i}").data["insertion_id"]
            for i, tab in enumerate(tabs)
        ]

        results = race_final_answers(tabs, insertion_ids)

        assert all(isinstance(r, Response) for r in results), results
        codes = sorted(r.status_code for r in results)
        assert codes == [200, 409], [r.data for r in results]
        loser = next(r for r in results if r.status_code == 409)
        assert loser.data == {"code": "list_changed"}
        assert positions(ranked.pk) == [0, 1]
        ranked.refresh_from_db()
        assert ranked.version == 1
        statuses = Insertion.objects.filter(pk__in=insertion_ids).values_list("status", flat=True)
        assert sorted(statuses) == ["abandoned", "done"]


@pytest.mark.django_db(transaction=True)
def test_double_click_from_two_connections_writes_one_answer(settings: Any) -> None:
    settings.PAIRRANK_DEFAULT_STRATEGY = "binary"
    owner = get_user_model().objects.create_user(username="guest-double")
    tabs = [APIClient(), APIClient()]
    for tab in tabs:
        tab.force_login(owner)

    for round_number in range(ROUNDS):
        ranked = RankList.objects.create(owner=owner, name=f"double {round_number}")
        fill_list(ranked.pk, 7, prefix=f"double{round_number}")
        insertion_id = start(tabs[0], ranked.pk, f"double {round_number}").data["insertion_id"]

        results = race_final_answers(tabs, [insertion_id, insertion_id])

        assert all(isinstance(r, Response) for r in results), results
        assert [r.status_code for r in results] == [200, 200]
        assert results[0].data == results[1].data
        assert Insertion.objects.get(pk=insertion_id).comparisons.count() == 1
