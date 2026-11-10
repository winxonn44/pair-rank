"""The five endpoints: happy paths, validation, idempotency, conflicts, ownership."""

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from ranking.models import Comparison, Insertion, ListEntry, Place
from ranking.tests.helpers import answer, fill_list, new_guest_list, positions, start

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def binary_strategy(settings: Any) -> None:
    """Binary insertion has predictable questions; the replay test covers the rest."""
    settings.PAIRRANK_DEFAULT_STRATEGY = "binary"


def test_app_default_strategy_is_bisection() -> None:
    from config import settings as project_settings

    assert project_settings.PAIRRANK_DEFAULT_STRATEGY == "bisection"


def test_first_place_needs_no_questions() -> None:
    client, list_id = new_guest_list()
    response = start(client, list_id, "Bestia")
    assert response.status_code == 201
    assert response.data["done"] is True
    assert response.data["position"] == 0
    assert response.data["list"]["version"] == 1
    assert response.data["list"]["entries"][0]["score"] == 10.0


def test_ranking_ten_places_ends_in_true_order_with_scores() -> None:
    client, list_id = new_guest_list()
    truth = [3, 8, 1, 6, 0, 9, 4, 2, 7, 5]  # lower number = better restaurant
    for rank in truth:
        response = start(client, list_id, f"place {rank}")
        insertion_id = response.data["insertion_id"]
        while not response.data.get("done"):
            question = response.data["question"]
            ref_rank = int(question["ref_place"]["name"].split()[-1])
            value = "better" if rank < ref_rank else "worse"
            response = answer(client, insertion_id, question["index"], value)
            assert response.status_code == 200

    body = client.get(f"/api/lists/{list_id}/").data
    assert [e["place"]["name"] for e in body["entries"]] == [f"place {i}" for i in range(10)]
    assert body["version"] == 10
    assert body["entries"][0]["score"] == 10.0
    assert body["entries"][-1]["score"] == 0.0
    assert positions(list_id) == list(range(10))


@pytest.mark.parametrize(("value", "slot"), [("better", 0), ("worse", 5)])
def test_shift_at_either_end(value: str, slot: int) -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 5)
    response = start(client, list_id)
    insertion_id = response.data["insertion_id"]
    while not response.data.get("done"):
        response = answer(client, insertion_id, response.data["question"]["index"], value)
    assert response.data["position"] == slot
    assert positions(list_id) == list(range(6))


def test_shift_in_the_middle() -> None:
    client, list_id = new_guest_list()
    places = fill_list(list_id, 5)
    response = start(client, list_id)
    insertion_id = response.data["insertion_id"]
    values = iter(["better", "worse", "better"])
    while not response.data.get("done"):
        response = answer(client, insertion_id, response.data["question"]["index"], next(values))
    slot = response.data["position"]
    assert 0 < slot < 5
    assert positions(list_id) == list(range(6))
    assert ListEntry.objects.get(list_id=list_id, position=slot + 1).place == places[slot]


def test_comparisons_are_logged() -> None:
    client, list_id = new_guest_list()
    places = fill_list(list_id, 3)
    response = start(client, list_id)
    question = response.data["question"]
    client.post(
        f"/api/insertions/{response.data['insertion_id']}/answers/",
        {"question_index": 0, "answer": "worse", "response_ms": 1234},
    )
    row = Comparison.objects.get()
    assert (row.question_index, row.ref_position) == (0, question["ref_position"])
    assert row.ref_place == places[question["ref_position"]]
    assert (row.answer, row.response_ms) == ("worse", 1234)


def test_tier_reaches_the_list_entry() -> None:
    client, list_id = new_guest_list()
    response = start(client, list_id, "Bavel", tier="liked")
    assert response.data["list"]["entries"][0]["tier"] == "liked"


def test_existing_place_is_reused_ignoring_case() -> None:
    Place.objects.create(name="Bestia", city="Los Angeles")
    client, list_id = new_guest_list()
    response = start(client, list_id, "  BESTIA ")
    assert response.data["list"]["entries"][0]["place"]["name"] == "Bestia"
    assert Place.objects.count() == 1


def test_place_already_in_the_list_is_a_conflict() -> None:
    client, list_id = new_guest_list()
    start(client, list_id, "Bestia")
    response = start(client, list_id, "bestia")
    assert response.status_code == 409
    assert response.data == {"code": "already_ranked"}
    assert Insertion.objects.count() == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"place_name": ""},
        {"place_name": "   "},
        {"place_name": "x" * 121},
        {"place_name": "ok", "tier": "amazing"},
    ],
)
def test_bad_start_is_a_400(body: dict[str, str]) -> None:
    client, list_id = new_guest_list()
    assert client.post(f"/api/lists/{list_id}/insertions/", body).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question_index": 0},
        {"question_index": 0, "answer": "maybe"},
        {"question_index": -1, "answer": "better"},
        {"question_index": 0, "answer": "better", "response_ms": -5},
    ],
)
def test_bad_answer_is_a_400(body: dict[str, object]) -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 3)
    insertion_id = start(client, list_id).data["insertion_id"]
    assert client.post(f"/api/insertions/{insertion_id}/answers/", body).status_code == 400
    assert Comparison.objects.count() == 0


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "x" * 101}])
def test_bad_list_is_a_400_and_creates_no_guest(body: dict[str, str]) -> None:
    assert APIClient().post("/api/lists/", body).status_code == 400
    assert get_user_model().objects.count() == 0


def test_duplicate_answer_repeats_the_response_without_writing() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 7)
    insertion_id = start(client, list_id).data["insertion_id"]
    first = answer(client, insertion_id, 0, "better")
    second = answer(client, insertion_id, 0, "better")
    assert second.status_code == 200
    assert second.data == first.data
    assert Comparison.objects.count() == 1
    assert Insertion.objects.get().n_questions == 1


def test_duplicate_of_an_earlier_answer_repeats_its_response() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 7)
    insertion_id = start(client, list_id).data["insertion_id"]
    first = answer(client, insertion_id, 0, "better")
    answer(client, insertion_id, 1, "worse")
    assert answer(client, insertion_id, 0, "better").data == first.data
    assert Comparison.objects.count() == 2


def test_duplicate_of_the_final_answer_repeats_done() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 1)
    insertion_id = start(client, list_id).data["insertion_id"]
    first = answer(client, insertion_id, 0, "worse")
    assert first.data["done"] is True
    assert answer(client, insertion_id, 0, "worse").data == first.data
    assert positions(list_id) == [0, 1]


def test_same_index_with_a_different_answer_is_a_conflict() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 7)
    insertion_id = start(client, list_id).data["insertion_id"]
    answer(client, insertion_id, 0, "better")
    response = answer(client, insertion_id, 0, "worse")
    assert response.status_code == 409
    assert response.data == {"code": "answer_mismatch"}
    assert Comparison.objects.count() == 1


def test_skipping_a_question_is_a_conflict() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 7)
    insertion_id = start(client, list_id).data["insertion_id"]
    response = answer(client, insertion_id, 3, "better")
    assert response.status_code == 409
    assert response.data == {"code": "question_out_of_order"}


def test_stale_insertion_gets_list_changed_and_is_closed() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 1)
    slow = start(client, list_id, "Slow").data["insertion_id"]
    fast = start(client, list_id, "Fast").data["insertion_id"]
    assert answer(client, fast, 0, "better").data["done"] is True

    response = answer(client, slow, 0, "better")
    assert response.status_code == 409
    assert response.data == {"code": "list_changed"}
    assert Insertion.objects.get(pk=slow).status == "abandoned"
    assert positions(list_id) == [0, 1]

    assert start(client, list_id, "Slow").status_code == 201  # the UI starts it again


def test_abandon_closes_the_insertion_and_is_repeatable() -> None:
    client, list_id = new_guest_list()
    fill_list(list_id, 3)
    insertion_id = start(client, list_id).data["insertion_id"]
    url = f"/api/insertions/{insertion_id}/abandon/"
    assert client.post(url).status_code == 204
    assert client.post(url).status_code == 204
    row = Insertion.objects.get()
    assert (row.status, row.final_position) == ("abandoned", None)
    assert row.finished_at is not None

    response = answer(client, insertion_id, 0, "better")
    assert response.status_code == 409
    assert response.data == {"code": "insertion_closed"}


def test_finished_insertion_cannot_be_abandoned() -> None:
    client, list_id = new_guest_list()
    insertion_id = start(client, list_id).data["insertion_id"]
    response = client.post(f"/api/insertions/{insertion_id}/abandon/")
    assert response.status_code == 409
    assert Insertion.objects.get().status == "done"


def test_unknown_ids_are_404() -> None:
    client, _ = new_guest_list()
    assert client.get("/api/lists/999999/").status_code == 404
    assert start(client, 999999).status_code == 404
    assert answer(client, 999999, 0, "better").status_code == 404
    assert client.post("/api/insertions/999999/abandon/").status_code == 404


def test_one_guest_cannot_touch_another_guests_data() -> None:
    owner, list_id = new_guest_list()
    fill_list(list_id, 3)
    insertion_id = start(owner, list_id).data["insertion_id"]
    other, _ = new_guest_list("mine")

    assert other.get(f"/api/lists/{list_id}/").status_code == 404
    assert start(other, list_id, "Intruder").status_code == 404
    assert answer(other, insertion_id, 0, "better").status_code == 404
    assert other.post(f"/api/insertions/{insertion_id}/abandon/").status_code == 404
    assert Comparison.objects.count() == 0


def test_anonymous_browser_sees_no_lists_and_cannot_write() -> None:
    owner, list_id = new_guest_list()
    anonymous = APIClient()
    assert anonymous.get("/api/lists/").data == []
    assert anonymous.get(f"/api/lists/{list_id}/").status_code == 403
    assert start(anonymous, list_id).status_code == 403


def test_a_guest_keeps_its_lists_across_requests() -> None:
    client, list_id = new_guest_list()
    assert client.post("/api/lists/", {"name": "NYC"}).status_code == 201
    assert get_user_model().objects.count() == 1
    assert [row["id"] for row in client.get("/api/lists/").data][0] == list_id
    assert len(client.get("/api/lists/").data) == 2


def test_guest_has_no_usable_password() -> None:
    new_guest_list()
    assert not get_user_model().objects.get().has_usable_password()


def test_first_post_without_csrf_token_is_rejected_and_creates_nothing() -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.post("/api/lists/", {"name": "LA"}).status_code == 403
    assert get_user_model().objects.count() == 0


def test_csrf_cookie_from_get_allows_the_first_and_later_posts() -> None:
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/lists/")
    token = client.cookies["csrftoken"].value
    first = client.post("/api/lists/", {"name": "LA"}, HTTP_X_CSRFTOKEN=token)
    assert first.status_code == 201

    # Logging the guest in rotates the token, so clients must read the cookie each time.
    token = client.cookies["csrftoken"].value
    second = client.post("/api/lists/", {"name": "NYC"}, HTTP_X_CSRFTOKEN=token)
    assert second.status_code == 201
    assert client.post("/api/lists/", {"name": "SF"}).status_code == 403


def test_throttle_returns_429_before_creating_a_guest(settings: Any) -> None:
    settings.API_THROTTLE_RATE = "2/min"
    cache.clear()
    client = APIClient()
    assert client.get("/api/lists/").status_code == 200
    assert client.get("/api/lists/").status_code == 200
    assert client.post("/api/lists/", {"name": "LA"}).status_code == 429
    assert get_user_model().objects.count() == 0
    cache.clear()
