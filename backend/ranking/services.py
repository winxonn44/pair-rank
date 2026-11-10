"""Every write the app makes. The placement logic itself lives in `pairrank.strategies`.

Each operation takes a row lock on the list, so two tabs inserting into one list
run one at a time. An insertion can only finish against the list it started on:
if another insertion finished in between, it is closed and the client gets a 409.
"""

import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from pairrank.scoring import percentile_scores
from pairrank.state import InsertionState
from pairrank.strategies import Placed, Query, Strategy, get_strategy
from ranking.models import (
    Answer,
    Comparison,
    Insertion,
    InsertionStatus,
    ListEntry,
    Place,
    RankList,
)

Payload = dict[str, Any]

# No current strategy draws random numbers; the field exists for ones that might.
STRATEGY_SEED = 0


class Conflict(APIException):
    """A 409 with a machine-readable code the front end can act on."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, code: str) -> None:
        self.detail = {"code": code}


def place_payload(place: Place) -> Payload:
    return {"id": place.pk, "name": place.name, "city": place.city}


def list_payload(ranked: RankList) -> Payload:
    """Scores are computed here on every read and never stored."""
    entries = list(ranked.entries.select_related("place").order_by("position"))
    scores = percentile_scores(len(entries))
    return {
        "id": ranked.pk,
        "name": ranked.name,
        "version": ranked.version,
        "entries": [
            {
                "place": place_payload(entry.place),
                "position": entry.position,
                "score": float(score),
                "tier": entry.tier,
            }
            for entry, score in zip(entries, scores, strict=True)
        ],
    }


def _question_payload(index: int, place: Place, position: int) -> Payload:
    return {
        "question": {"index": index, "ref_place": place_payload(place), "ref_position": position}
    }


def _done_payload(ranked: RankList, position: int) -> Payload:
    return {"done": True, "position": position, "list": list_payload(ranked)}


def _load_state(insertion: Insertion) -> InsertionState:
    return InsertionState.from_json(json.dumps(insertion.state))


def _entries_at(ranked: RankList, positions: list[int]) -> dict[int, ListEntry]:
    rows = ranked.entries.select_related("place").filter(position__in=positions)
    return {entry.position: entry for entry in rows}


def _get_or_create_place(name: str, city: str, user: Any) -> Place:
    """Case-insensitive lookup; ON CONFLICT keeps two simultaneous creators from failing."""
    matches = Place.objects.annotate(lower_name=Lower("name")).filter(
        lower_name=Lower(Value(name)), city=city
    )
    existing = matches.first()
    if existing is not None:
        return existing
    Place.objects.bulk_create(
        [Place(name=name.strip(), city=city, created_by=user)], ignore_conflicts=True
    )
    return matches.get()


def _finish(ranked: RankList, insertion: Insertion, state: InsertionState, slot: int) -> None:
    """Open a gap at `slot` and fill it. The deferred constraint allows the shift."""
    ranked.entries.filter(position__gte=slot).update(position=F("position") + 1)
    ListEntry.objects.create(
        list=ranked, place_id=insertion.place_id, position=slot, tier=insertion.tier
    )
    ranked.version += 1
    ranked.save(update_fields=["version"])
    insertion.state = json.loads(state.to_json())
    insertion.n_questions = state.n_questions
    insertion.status = InsertionStatus.DONE
    insertion.final_position = slot
    insertion.finished_at = timezone.now()
    insertion.save(
        update_fields=["state", "n_questions", "status", "final_position", "finished_at"]
    )


def _close_abandoned(insertion: Insertion) -> None:
    insertion.status = InsertionStatus.ABANDONED
    insertion.finished_at = timezone.now()
    insertion.save(update_fields=["status", "finished_at"])


def start_insertion(
    user: Any, list_id: int, place_name: str, city: str, tier: str | None = None
) -> Payload:
    with transaction.atomic():
        ranked = get_object_or_404(RankList.objects.select_for_update(), pk=list_id, owner=user)
        place = _get_or_create_place(place_name, city, user)
        if ranked.entries.filter(place=place).exists():
            raise Conflict("already_ranked")

        strategy = get_strategy(settings.PAIRRANK_DEFAULT_STRATEGY)
        n = ranked.entries.count()
        state = strategy.start(n, STRATEGY_SEED)
        insertion = Insertion.objects.create(
            list=ranked,
            place=place,
            strategy=strategy.name,
            tier=tier,
            state=json.loads(state.to_json()),
            list_version_at_start=ranked.version,
        )
        step = strategy.next_query(state)
        if isinstance(step, Placed):
            _finish(ranked, insertion, state, step.slot)
            return {"insertion_id": insertion.pk, **_done_payload(ranked, step.slot)}
        entry = _entries_at(ranked, [step.ref_position])[step.ref_position]
        return {
            "insertion_id": insertion.pk,
            **_question_payload(0, entry.place, step.ref_position),
        }


def _lock_insertion(user: Any, insertion_id: int) -> Insertion:
    """Lock the insertion and its list together, in one query."""
    rows = Insertion.objects.select_for_update(of=("self", "list")).select_related("list")
    return get_object_or_404(rows, pk=insertion_id, list__owner=user)


def _is_stale(insertion: Insertion) -> bool:
    return (
        insertion.status == InsertionStatus.OPEN
        and insertion.list_version_at_start != insertion.list.version
    )


def _repeat_response(
    insertion: Insertion, strategy: Strategy, state: InsertionState, index: int, answer: str
) -> Payload:
    """A retry of an answer already recorded: same response, no writes."""
    if state.answers[index][1] != (answer == Answer.BETTER):
        raise Conflict("answer_mismatch")
    prefix = InsertionState(state.strategy, state.n, state.answers[: index + 1], state.seed)
    step = strategy.next_query(prefix)
    if isinstance(step, Placed):
        return _done_payload(insertion.list, step.slot)
    following = index + 1
    if following < len(state.answers):
        place = (
            insertion.comparisons.select_related("ref_place")
            .get(question_index=following)
            .ref_place
        )
    else:
        place = _entries_at(insertion.list, [step.ref_position])[step.ref_position].place
    return _question_payload(following, place, step.ref_position)


def _record_answer(
    insertion: Insertion,
    strategy: Strategy,
    state: InsertionState,
    answer: str,
    response_ms: int | None,
) -> Payload:
    ranked = insertion.list
    asked = strategy.next_query(state)
    if not isinstance(asked, Query):
        raise ValueError("an open insertion must have a question to answer")
    new_state = strategy.observe(state, asked.ref_position, answer == Answer.BETTER)
    step = strategy.next_query(new_state)

    wanted = (
        [asked.ref_position]
        if isinstance(step, Placed)
        else [asked.ref_position, step.ref_position]
    )
    entries = _entries_at(ranked, wanted)
    Comparison.objects.create(
        insertion=insertion,
        question_index=state.n_questions,
        ref_place=entries[asked.ref_position].place,
        ref_position=asked.ref_position,
        answer=answer,
        response_ms=response_ms,
    )
    if isinstance(step, Placed):
        _finish(ranked, insertion, new_state, step.slot)
        return _done_payload(ranked, step.slot)

    insertion.state = json.loads(new_state.to_json())
    insertion.n_questions = new_state.n_questions
    insertion.save(update_fields=["state", "n_questions"])
    return _question_payload(
        new_state.n_questions, entries[step.ref_position].place, step.ref_position
    )


def answer_question(
    user: Any, insertion_id: int, question_index: int, answer: str, response_ms: int | None = None
) -> Payload:
    with transaction.atomic():
        insertion = _lock_insertion(user, insertion_id)
        if _is_stale(insertion):
            _close_abandoned(insertion)  # outside the raise, so this write commits
        else:
            if insertion.status == InsertionStatus.ABANDONED:
                raise Conflict("insertion_closed")
            state = _load_state(insertion)
            strategy = get_strategy(insertion.strategy)
            if question_index < state.n_questions:
                return _repeat_response(insertion, strategy, state, question_index, answer)
            if insertion.status == InsertionStatus.DONE:
                raise Conflict("insertion_closed")
            if question_index > state.n_questions:
                raise Conflict("question_out_of_order")
            return _record_answer(insertion, strategy, state, answer, response_ms)
    raise Conflict("list_changed")


def abandon_insertion(user: Any, insertion_id: int) -> None:
    with transaction.atomic():
        insertion = _lock_insertion(user, insertion_id)
        if insertion.status == InsertionStatus.DONE:
            raise Conflict("insertion_closed")
        if insertion.status == InsertionStatus.OPEN:
            _close_abandoned(insertion)
