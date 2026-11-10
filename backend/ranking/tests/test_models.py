"""Constraint tests, run on Postgres because SQLite handles deferral differently."""

import json

import pytest
from config.settings import parse_database_url
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from pairrank.state import InsertionState
from ranking.models import Comparison, Insertion, ListEntry, Place, RankList

pytestmark = pytest.mark.django_db


def make_list(n: int, owner_name: str = "guest") -> RankList:
    """A list with n entries at positions 0..n-1, created best-first."""
    owner = get_user_model().objects.create(username=owner_name)
    ranked = RankList.objects.create(owner=owner, name="LA")
    for i in range(n):
        place = Place.objects.create(name=f"{owner_name} place {i}", city="Los Angeles")
        ListEntry.objects.create(list=ranked, place=place, position=i)
    return ranked


def make_insertion(ranked: RankList, **kwargs: object) -> Insertion:
    place = Place.objects.create(name=f"new {Place.objects.count()}", city="Los Angeles")
    state = InsertionState(strategy="binary", n=ranked.entries.count())
    return Insertion.objects.create(
        list=ranked,
        place=place,
        strategy="binary",
        state=json.loads(state.to_json()),
        list_version_at_start=ranked.version,
        **kwargs,
    )


def shift_down_from(ranked: RankList, slot: int) -> None:
    """The one statement that makes room for a new entry at `slot`."""
    ranked.entries.filter(position__gte=slot).update(position=F("position") + 1)


def positions(ranked: RankList) -> list[int]:
    return list(ranked.entries.order_by("position").values_list("position", flat=True))


def test_position_constraint_is_deferred_in_the_catalog() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT condeferrable, condeferred FROM pg_constraint WHERE conname = %s",
            ["uniq_entry_list_position"],
        )
        assert cursor.fetchone() == (True, True)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("slot", [0, 2, 5])
def test_shift_and_insert_commits_with_deferred_constraint(slot: int) -> None:
    ranked = make_list(5)
    new_place = Place.objects.create(name="new", city="Los Angeles")

    with transaction.atomic():
        shift_down_from(ranked, slot)
        ListEntry.objects.create(list=ranked, place=new_place, position=slot)

    assert positions(ranked) == [0, 1, 2, 3, 4, 5]
    assert ranked.entries.get(place=new_place).position == slot


def test_same_shift_fails_under_a_non_deferred_constraint() -> None:
    """Counterpart to the test above: this is why the constraint has to be deferred.

    DDL is transactional on Postgres, so the swap is undone when the test ends.
    """
    ranked = make_list(5)
    with connection.cursor() as cursor:
        # Postgres refuses ALTER TABLE while deferred checks from make_list are pending.
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("ALTER TABLE ranking_listentry DROP CONSTRAINT uniq_entry_list_position")
        cursor.execute(
            "ALTER TABLE ranking_listentry ADD CONSTRAINT uniq_entry_list_position "
            "UNIQUE (list_id, position)"
        )

    with pytest.raises(IntegrityError, match="uniq_entry_list_position"), transaction.atomic():
        shift_down_from(ranked, 0)


@pytest.mark.django_db(transaction=True)
def test_duplicate_position_is_rejected_at_commit() -> None:
    ranked = make_list(2)
    other = Place.objects.create(name="other", city="Los Angeles")

    with pytest.raises(IntegrityError, match="uniq_entry_list_position"), transaction.atomic():
        # The insert itself succeeds; the collision only surfaces at commit.
        ListEntry.objects.create(list=ranked, place=other, position=1)

    assert ranked.entries.count() == 2


def test_two_lists_can_use_the_same_position_and_place() -> None:
    first = make_list(1, "a")
    second = make_list(1, "b")
    shared = first.entries.get().place
    second_place = second.entries.get()
    second_place.place = shared
    second_place.save()
    assert ListEntry.objects.filter(place=shared, position=0).count() == 2


def test_duplicate_place_in_a_list_is_rejected_immediately() -> None:
    ranked = make_list(2)
    place = ranked.entries.get(position=0).place
    with pytest.raises(IntegrityError, match="uniq_entry_list_place"), transaction.atomic():
        ListEntry.objects.create(list=ranked, place=place, position=2)


def test_negative_position_is_rejected() -> None:
    ranked = make_list(1)
    with pytest.raises(IntegrityError), transaction.atomic():
        ranked.entries.update(position=-1)


def test_invalid_tier_is_rejected() -> None:
    ranked = make_list(1)
    with pytest.raises(IntegrityError, match="entry_tier_valid"), transaction.atomic():
        ranked.entries.update(tier="amazing")


def test_place_name_is_unique_ignoring_case_within_a_city() -> None:
    Place.objects.create(name="Bestia", city="Los Angeles")
    with pytest.raises(IntegrityError, match="uniq_place_lower_name_city"), transaction.atomic():
        Place.objects.create(name="BESTIA", city="Los Angeles")
    Place.objects.create(name="Bestia", city="New York")


def test_place_name_is_trimmed_on_save() -> None:
    place = Place.objects.create(name="  Bavel  ", city="Los Angeles")
    place.refresh_from_db()
    assert place.name == "Bavel"


@pytest.mark.parametrize("bad_name", [" padded ", ""])
def test_database_rejects_untrimmed_or_empty_names(bad_name: str) -> None:
    place = Place.objects.create(name="ok", city="Los Angeles")
    with pytest.raises(IntegrityError, match="place_name_trimmed"), transaction.atomic():
        Place.objects.filter(pk=place.pk).update(name=bad_name)


def test_insertion_state_round_trips_through_jsonb() -> None:
    state = InsertionState(strategy="bisection", n=49, answers=((24, True), (11, False)), seed=7)
    insertion = make_insertion(make_list(1))
    insertion.state = json.loads(state.to_json())
    insertion.save()

    stored = Insertion.objects.get(pk=insertion.pk).state
    assert InsertionState.from_json(json.dumps(stored)) == state
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'ranking_insertion' AND column_name = 'state'"
        )
        assert cursor.fetchone() == ("jsonb",)


def test_done_insertion_needs_a_result() -> None:
    with pytest.raises(IntegrityError, match="insertion_done_has_result"), transaction.atomic():
        make_insertion(make_list(1), status="done")


def test_done_insertion_with_a_result_is_accepted() -> None:
    insertion = make_insertion(
        make_list(1), status="done", final_position=0, finished_at=timezone.now()
    )
    assert insertion.pk is not None


def test_open_insertion_cannot_have_a_final_position() -> None:
    with pytest.raises(IntegrityError, match="insertion_done_has_result"), transaction.atomic():
        make_insertion(make_list(1), final_position=0)


def test_abandoned_insertion_is_kept_without_a_result() -> None:
    insertion = make_insertion(make_list(1), status="abandoned")
    assert Insertion.objects.filter(pk=insertion.pk, status="abandoned").exists()


def test_invalid_insertion_status_is_rejected() -> None:
    with pytest.raises(IntegrityError, match="insertion_status_valid"), transaction.atomic():
        make_insertion(make_list(1), status="paused")


def make_comparison(insertion: Insertion, index: int, answer: str = "better") -> Comparison:
    entry = insertion.list.entries.get(position=0)
    return Comparison.objects.create(
        insertion=insertion,
        question_index=index,
        ref_place=entry.place,
        ref_position=entry.position,
        answer=answer,
    )


def test_duplicate_question_index_is_rejected() -> None:
    insertion = make_insertion(make_list(1))
    make_comparison(insertion, 0)
    duplicate_index = pytest.raises(IntegrityError, match="uniq_comparison_insertion_index")
    with duplicate_index, transaction.atomic():
        make_comparison(insertion, 0, "worse")
    assert insertion.comparisons.count() == 1


def test_invalid_answer_is_rejected() -> None:
    insertion = make_insertion(make_list(1))
    with pytest.raises(IntegrityError, match="comparison_answer_valid"), transaction.atomic():
        make_comparison(insertion, 0, "maybe")


def test_seed_fixture_loads_and_ids_keep_counting() -> None:
    call_command("loaddata", "la_places", verbosity=0)
    assert Place.objects.count() == 40
    assert Place.objects.filter(city="Los Angeles", created_by=None).count() == 40
    # loaddata uses explicit ids; the next ordinary insert must not collide with them.
    assert Place.objects.create(name="A new spot", city="Los Angeles").pk > 40


def test_models_and_migrations_agree() -> None:
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgres://u:p%40ss@db.example.com:6543/app?sslmode=require",
            {
                "USER": "u",
                "PASSWORD": "p@ss",
                "HOST": "db.example.com",
                "PORT": "6543",
                "NAME": "app",
                "OPTIONS": {"sslmode": "require"},
            },
        ),
        (
            "postgresql://u@localhost/app",
            {"USER": "u", "PASSWORD": "", "HOST": "localhost", "PORT": "", "OPTIONS": {}},
        ),
    ],
)
def test_parse_database_url(url: str, expected: dict[str, object]) -> None:
    parsed = parse_database_url(url)
    assert parsed["ENGINE"] == "django.db.backends.postgresql"
    assert {key: parsed[key] for key in expected} == expected
