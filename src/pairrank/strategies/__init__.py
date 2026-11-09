"""Placement strategies. S3b (Bradley-Terry active querying) arrives in checkpoint S1b."""

from pairrank.strategies.base import Placed, Query, Step, Strategy
from pairrank.strategies.binary import BinaryInsertion
from pairrank.strategies.bisection import BisectionInsertion
from pairrank.strategies.majority import MajorityInsertion, NeighborMajorityInsertion
from pairrank.strategies.verify import VerifyInsertion

_REGISTRY: dict[str, type[Strategy]] = {
    BinaryInsertion.name: BinaryInsertion,
    MajorityInsertion.name: MajorityInsertion,
    NeighborMajorityInsertion.name: NeighborMajorityInsertion,
    BisectionInsertion.name: BisectionInsertion,
    VerifyInsertion.name: VerifyInsertion,
}


def get_strategy(name: str) -> Strategy:
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"unknown strategy {name!r}; known: {sorted(_REGISTRY)}") from None


__all__ = [
    "BinaryInsertion",
    "BisectionInsertion",
    "MajorityInsertion",
    "NeighborMajorityInsertion",
    "Placed",
    "Query",
    "Step",
    "Strategy",
    "VerifyInsertion",
    "get_strategy",
]
