"""Placement strategies. S2-S4 arrive in checkpoint S1."""

from pairrank.strategies.base import Placed, Query, Step, Strategy
from pairrank.strategies.binary import BinaryInsertion

_REGISTRY: dict[str, type[Strategy]] = {
    BinaryInsertion.name: BinaryInsertion,
}


def get_strategy(name: str) -> Strategy:
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"unknown strategy {name!r}; known: {sorted(_REGISTRY)}") from None


__all__ = ["BinaryInsertion", "Placed", "Query", "Step", "Strategy", "get_strategy"]
