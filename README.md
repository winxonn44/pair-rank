# PairRank

[![CI](https://github.com/winxonn44/pair-rank/actions/workflows/ci.yml/badge.svg)](https://github.com/winxonn44/pair-rank/actions/workflows/ci.yml)

> **A note on inspiration.** PairRank was inspired by Beli,
> the restaurant-ranking app, which asks "better or worse?" instead of asking for
> star ratings. This project is not a copy of Beli and doesn't try to reproduce
> its algorithms, scores or design. It's an independent, experimental study of
> how ranking-by-comparison algorithms for personal taste behave when people
> answer inconsistently. It isn't affiliated with Beli and uses no Beli data.

How few "better or worse?" questions does it take to place a new restaurant in
someone's ranked list when people answer inconsistently, and what does that do
to the 0–10 scores they see?

PairRank is a simulation study plus a small app in Django, PostgreSQL and
Angular. Every experiment uses simulated users with known true preferences, so
placement error can be measured exactly. The A/B test runs both offline and end
to end through the app on one machine. No data is collected from people.

**Status:** checkpoint S0. The simulator matches an exact oracle; strategy
comparisons come next. Measured results so far are in
[`docs/RESULTS.md`](docs/RESULTS.md).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/python scripts/s0_oracle_check.py   # simulator vs exact oracle
```

## Design notes

- [`docs/DECISIONS.md`](docs/DECISIONS.md): every design decision, with the reason and what was measured.
