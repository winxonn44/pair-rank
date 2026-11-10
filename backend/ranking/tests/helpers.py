"""Shared setup for the API tests."""

from typing import Any

from rest_framework.response import Response
from rest_framework.test import APIClient

from ranking.models import ListEntry, Place, RankList


def new_guest_list(name: str = "LA") -> tuple[APIClient, int]:
    """A fresh browser: its first POST creates the guest and logs it in."""
    client = APIClient()
    response = client.post("/api/lists/", {"name": name})
    assert response.status_code == 201
    return client, response.data["id"]


def fill_list(list_id: int, n: int, prefix: str = "entry") -> list[Place]:
    """Add n places directly, at positions 0..n-1, and return them best-first."""
    places = Place.objects.bulk_create(
        [Place(name=f"{prefix} {list_id} {i}", city="Los Angeles") for i in range(n)]
    )
    ListEntry.objects.bulk_create(
        [ListEntry(list_id=list_id, place=p, position=i) for i, p in enumerate(places)]
    )
    return places


def start(client: APIClient, list_id: int, name: str = "New Spot", **extra: Any) -> Response:
    return client.post(f"/api/lists/{list_id}/insertions/", {"place_name": name, **extra})


def answer(client: APIClient, insertion_id: int, index: int, value: str) -> Response:
    return client.post(
        f"/api/insertions/{insertion_id}/answers/", {"question_index": index, "answer": value}
    )


def positions(list_id: int) -> list[int]:
    entries = RankList.objects.get(pk=list_id).entries.order_by("position")
    return list(entries.values_list("position", flat=True))
