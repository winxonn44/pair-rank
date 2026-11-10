"""The headline check: the API places restaurants exactly where the simulator does.

Transcripts come from `pairrank.sim.session`, which never touches Django. Each one
is replayed over HTTP, and the question order, final position, question count and
logged comparison rows must all match.
"""

from typing import Any

import numpy as np
import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.test import APIClient

from pairrank.sim.noise import ConstantNoise
from pairrank.sim.session import InsertionResult, build_list, simulate_insertions
from pairrank.strategies import get_strategy
from ranking.models import Insertion, ListEntry, Place, RankList
from ranking.tests.helpers import answer, start

pytestmark = pytest.mark.django_db

STRATEGIES = ["binary", "majority", "majority-neighbor", "bisection", "verify"]
EPSILONS = [0.0, 0.1, 0.2]
LIST_SIZES = [0, 1, 2, 7, 20, 50]
TRANSCRIPTS_PER_CELL = 12
N_REPLAY = len(STRATEGIES) * len(EPSILONS) * len(LIST_SIZES) * TRANSCRIPTS_PER_CELL
MASTER_SEED = 20261109


def rng_for(*key: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([MASTER_SEED, *key])))


def replay(client: APIClient, owner: object, pool: list[Place], result: InsertionResult, i: int):
    ranked = RankList.objects.create(owner=owner, name=f"replay {i}")
    ListEntry.objects.bulk_create(
        [ListEntry(list=ranked, place=pool[j], position=j) for j in range(result.n)]
    )

    response = start(client, ranked.pk, f"replayed place {i}")
    assert response.status_code == 201
    insertion_id = response.data["insertion_id"]
    for index, (position, new_is_better) in enumerate(result.answers):
        assert response.data["question"]["index"] == index
        assert response.data["question"]["ref_position"] == position
        value = "better" if new_is_better else "worse"
        response = answer(client, insertion_id, index, value)
        assert response.status_code == 200

    assert response.data["done"] is True
    assert response.data["position"] == result.slot

    row = Insertion.objects.get(pk=insertion_id)
    assert row.strategy == result.strategy
    assert row.n_questions == result.n_questions
    assert row.final_position == result.slot
    logged = list(
        row.comparisons.order_by("question_index").values_list(
            "question_index", "ref_position", "ref_place_id", "answer"
        )
    )
    assert logged == [
        (index, position, pool[position].pk, "better" if better else "worse")
        for index, (position, better) in enumerate(result.answers)
    ]

    entries = list(ranked.entries.order_by("position").values_list("position", "place__name"))
    assert [position for position, _ in entries] == list(range(result.n + 1))
    assert entries[result.slot][1] == f"replayed place {i}"


def test_replay_count_is_what_the_docs_report() -> None:
    assert N_REPLAY == 1080


def test_simulated_transcripts_replay_identically(settings: Any) -> None:
    owner = get_user_model().objects.create_user(username="guest-replay")
    client = APIClient()
    client.force_login(owner)
    pool = Place.objects.bulk_create(
        [Place(name=f"pool {j}", city="Los Angeles") for j in range(max(LIST_SIZES))]
    )

    replayed = 0
    for s, name in enumerate(STRATEGIES):
        settings.PAIRRANK_DEFAULT_STRATEGY = name
        for e, eps in enumerate(EPSILONS):
            for n in LIST_SIZES:
                results = simulate_insertions(
                    get_strategy(name),
                    n,
                    ConstantNoise(eps),
                    TRANSCRIPTS_PER_CELL,
                    rng_for(s, e, n),
                )
                for result in results:
                    replay(client, owner, pool, result, replayed)
                    replayed += 1
    connection.check_constraints()  # fires the deferred checks a commit would run
    assert replayed == N_REPLAY


@pytest.mark.parametrize("name", STRATEGIES)
def test_whole_session_builds_the_same_list(name: str, settings: Any) -> None:
    """Successive insertions, each one depending on earlier mistakes."""
    settings.PAIRRANK_DEFAULT_STRATEGY = name
    size = 30
    eps = 0.15
    key = STRATEGIES.index(name) + 1000
    utilities = rng_for(key).standard_normal(size)
    offline = build_list(get_strategy(name), utilities, ConstantNoise(eps), rng_for(key, 1))

    client = APIClient()
    assert client.post("/api/lists/", {"name": "session"}).status_code == 201
    list_id = client.get("/api/lists/").data[0]["id"]
    noise = ConstantNoise(eps).fresh()
    rng = rng_for(key, 1)
    questions = 0
    order: list[int] = []
    for new_id in range(size):
        response = start(client, list_id, f"session place {new_id}")
        insertion_id = response.data["insertion_id"]
        while not response.data.get("done"):
            question = response.data["question"]
            ref_id = order[question["ref_position"]]
            better = noise.answer(
                float(utilities[new_id]), float(utilities[ref_id]), rng, (new_id, ref_id)
            )
            value = "better" if better else "worse"
            response = answer(client, insertion_id, question["index"], value)
            assert response.status_code == 200
            questions += 1
        order.insert(response.data["position"], new_id)

    names = [e["place"]["name"] for e in client.get(f"/api/lists/{list_id}/").data["entries"]]
    assert names == [f"session place {i}" for i in offline.order]
    assert tuple(order) == offline.order
    assert questions == offline.n_questions
