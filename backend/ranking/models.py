"""The app's schema. Positions are stored; 0-10 scores are computed on read.

Positions follow docs/conventions.md: 0-indexed, 0 is the best entry, and a list
of n entries occupies exactly positions 0 to n - 1.
"""

from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Deferrable, F, Q
from django.db.models.functions import Lower, Trim


class Place(models.Model):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("name"), "city", name="uniq_place_lower_name_city"),
            models.CheckConstraint(
                condition=Q(name=Trim(F("name"))) & ~Q(name=""), name="place_name_trimmed"
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"


class RankList(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rank_lists"
    )
    name = models.CharField(max_length=100)
    version = models.PositiveIntegerField(default=0)  # +1 on every completed insertion
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Tier(models.TextChoices):
    DISLIKED = "disliked"
    FINE = "fine"
    LIKED = "liked"


class ListEntry(models.Model):
    list = models.ForeignKey(RankList, on_delete=models.CASCADE, related_name="entries")
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="entries")
    position = models.PositiveIntegerField()
    tier = models.CharField(max_length=8, choices=Tier.choices, null=True, blank=True)

    class Meta:
        ordering = ["list", "position"]
        verbose_name_plural = "list entries"
        constraints = [
            # Deferred to commit: `SET position = position + 1` collides with the
            # next row part-way through the statement under a non-deferred constraint.
            models.UniqueConstraint(
                fields=["list", "position"],
                name="uniq_entry_list_position",
                deferrable=Deferrable.DEFERRED,
            ),
            models.UniqueConstraint(fields=["list", "place"], name="uniq_entry_list_place"),
            models.CheckConstraint(
                condition=Q(tier__isnull=True) | Q(tier__in=Tier.values), name="entry_tier_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.position + 1} in list {self.list_id}"


class InsertionStatus(models.TextChoices):
    OPEN = "open"
    DONE = "done"
    ABANDONED = "abandoned"


class Insertion(models.Model):
    """One attempt to place a restaurant, kept even if abandoned: the funnel table."""

    list = models.ForeignKey(RankList, on_delete=models.CASCADE, related_name="insertions")
    place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="insertions")
    strategy = models.CharField(max_length=32)
    state = models.JSONField()  # pairrank.state.InsertionState, as JSONB
    list_version_at_start = models.PositiveIntegerField()
    n_questions = models.PositiveIntegerField(default=0)
    final_position = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=9, choices=InsertionStatus.choices, default=InsertionStatus.OPEN
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=InsertionStatus.values), name="insertion_status_valid"
            ),
            # Only a finished insertion has a final position and a finish time.
            models.CheckConstraint(
                condition=(
                    Q(
                        status=InsertionStatus.DONE,
                        final_position__isnull=False,
                        finished_at__isnull=False,
                    )
                    | (~Q(status=InsertionStatus.DONE) & Q(final_position__isnull=True))
                ),
                name="insertion_done_has_result",
            ),
        ]

    def __str__(self) -> str:
        return f"insertion {self.pk} ({self.status})"


class Answer(models.TextChoices):
    BETTER = "better"
    WORSE = "worse"


class Comparison(models.Model):
    """One answered question. Rows are only ever added."""

    insertion = models.ForeignKey(Insertion, on_delete=models.CASCADE, related_name="comparisons")
    question_index = models.PositiveIntegerField()
    ref_place = models.ForeignKey(Place, on_delete=models.PROTECT, related_name="+")
    ref_position = models.PositiveIntegerField()
    answer = models.CharField(max_length=6, choices=Answer.choices)
    response_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["insertion", "question_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["insertion", "question_index"], name="uniq_comparison_insertion_index"
            ),
            models.CheckConstraint(
                condition=Q(answer__in=Answer.values), name="comparison_answer_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"Q{self.question_index}: {self.answer}"
