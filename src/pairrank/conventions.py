"""Project-wide conventions. docs/conventions.md (checkpoint S0) explains each one.

Every constant here has a test in tests/test_conventions.py.
"""

from typing import Final, Literal

# Positions are 0-indexed and 0 is the best entry. Display rank = position + 1.
BEST_POSITION: Final = 0

# Scores: 10 is best, 0 is worst. Floats internally; rounded only for display.
SCORE_MIN: Final = 0.0
SCORE_MAX: Final = 10.0
DISPLAY_DECIMALS: Final = 1

# Tiered mapping: the user picks a tier, then compares only within it.
Tier = Literal["disliked", "fine", "liked"]
TIER_BANDS: Final[dict[Tier, tuple[float, float]]] = {
    "disliked": (0.0, 10.0 / 3.0),
    "fine": (10.0 / 3.0, 20.0 / 3.0),
    "liked": (20.0 / 3.0, 10.0),
}

# Default answer-error rate in simulations and the assumed rate in Bayesian strategies.
DEFAULT_EPS: Final = 0.10


def display_rank(position: int) -> int:
    """Rank shown to a user (1 = best) for an internal 0-indexed position."""
    if position < 0:
        raise ValueError(f"position must be >= 0, got {position}")
    return position + 1


def display_score(score: float) -> float:
    """Score as shown to a user: rounded to DISPLAY_DECIMALS."""
    return round(score, DISPLAY_DECIMALS)
