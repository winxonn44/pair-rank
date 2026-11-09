"""The strategy interface shared by the simulator and the app."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pairrank.state import InsertionState


@dataclass(frozen=True)
class Query:
    """Ask: is the new place better than the entry at `ref_position`?"""

    ref_position: int


@dataclass(frozen=True)
class Placed:
    """The insertion is finished: the new place goes into `slot` (0..n)."""

    slot: int


Step = Query | Placed


class Strategy(ABC):
    """A pure state machine: start -> (next_query -> observe)* -> Placed."""

    name: ClassVar[str]

    def start(self, n: int, seed: int = 0) -> InsertionState:
        return InsertionState(strategy=self.name, n=n, seed=seed)

    @abstractmethod
    def _next(self, state: InsertionState) -> Step:
        """The next step, computed from the transcript alone."""

    def next_query(self, state: InsertionState) -> Step:
        self._check(state)
        return self._next(state)

    def observe(
        self, state: InsertionState, ref_position: int, new_is_better: bool
    ) -> InsertionState:
        step = self.next_query(state)
        if isinstance(step, Placed):
            raise ValueError("this insertion is already placed")
        if step.ref_position != ref_position:
            raise ValueError(
                f"answer is for position {ref_position}, but the strategy asked about "
                f"{step.ref_position}"
            )
        return state.with_answer(ref_position, new_is_better)

    def _check(self, state: InsertionState) -> None:
        if state.strategy != self.name:
            raise ValueError(f"state belongs to {state.strategy!r}, not {self.name!r}")
