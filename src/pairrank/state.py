"""Insertion state: the transcript of one insertion, which round-trips through JSON.

A strategy keeps no hidden state. Everything it needs (search interval,
posterior, ...) is recomputed from `answers`, so storing this object (for
example in the app's `Insertion.state` column) is enough to resume or replay.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Any

Answer = tuple[int, bool]  # (position asked, new_is_better)


@dataclass(frozen=True)
class InsertionState:
    strategy: str
    n: int
    answers: tuple[Answer, ...] = ()
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n < 0:
            raise ValueError(f"list size must be >= 0, got {self.n}")

    def with_answer(self, ref_position: int, new_is_better: bool) -> InsertionState:
        return dataclasses.replace(self, answers=(*self.answers, (ref_position, new_is_better)))

    @property
    def n_questions(self) -> int:
        return len(self.answers)

    def to_json(self) -> str:
        payload = {
            "strategy": self.strategy,
            "n": self.n,
            "answers": [[j, b] for j, b in self.answers],
            "seed": self.seed,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> InsertionState:
        data: dict[str, Any] = json.loads(text)
        answers: list[Answer] = []
        for item in data["answers"]:
            j, b = item
            if not isinstance(j, int) or isinstance(j, bool) or not isinstance(b, bool):
                raise ValueError(f"malformed answer {item!r}")
            answers.append((j, b))
        return cls(
            strategy=str(data["strategy"]),
            n=int(data["n"]),
            answers=tuple(answers),
            seed=int(data["seed"]),
        )
