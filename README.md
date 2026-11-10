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

**Status:** the simulation results and the app's API on Postgres are done; the Angular front end
comes next. Everything below comes from simulated users, and each row can be regenerated with its
script.

| Result | Measured | Source |
|---|---|---|
| **Placement** (list of 49, 10% wrong answers) | Binary insertion: 2.88 positions off in 5.6 questions. Bayesian bisection: 0.20 in 10.9. The gain shrinks when mistakes concentrate on close pairs or repeat | `runs/q1.jsonl` |
| **Score drift** | A 0–10 score moves about 0.94 points as a list grows from 10 to 50, even with perfect answers, within 2.3% of the drift law | `runs/q2.jsonl` |
| **A/B test design** | 481 users per arm detect a 0.25-position improvement at 80% power, checked by 2,000 simulated experiments (A/A false-positive rate 4.35%) | `runs/q4.jsonl` |
| **App matches simulator** | 1,080 simulated transcripts replayed through the API gave identical questions, final positions and logged comparisons | `backend/ranking/tests/test_replay.py` |
| **SQL metrics** | 8 PostgreSQL queries on 50,000 simulated insertions equal independent pandas versions (largest difference 6e-14) | `runs/s4.jsonl` |

Hypotheses that failed are kept in [`docs/RESULTS.md`](docs/RESULTS.md).

![Average placement error against questions asked](docs/figures/q1_error_vs_questions.png)

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/python scripts/s0_oracle_check.py   # simulator vs exact oracle
.venv/bin/python scripts/q1_placement.py      # Q1 grid, about 5 min on 8 cores
.venv/bin/python scripts/q2_drift.py          # Q2, about 30 s
.venv/bin/python scripts/q4_abtest.py         # Q4, about 3 min
.venv/bin/python scripts/load_sim_to_pg.py    # SQL metrics, needs Postgres (below), about 15 s
.venv/bin/python scripts/make_figures.py      # every figure and table
```

The app needs Docker for PostgreSQL 17 (bound to localhost only):

```bash
.venv/bin/pip install -e ".[dev,backend]"
docker compose up -d --wait
cd backend
DEBUG=1 ../.venv/bin/python manage.py migrate
DEBUG=1 ../.venv/bin/python manage.py loaddata la_places
../.venv/bin/pytest
```

## API

Guests need no account: a browser's first `POST /api/lists/` creates one, tied to its session
cookie. With the server running (`DEBUG=1 ../.venv/bin/python manage.py runserver`):

```bash
JAR=$(mktemp)
csrf() { awk '$6 == "csrftoken" { print $7 }' "$JAR"; }
post() { curl -s -b "$JAR" -c "$JAR" -H "Content-Type: application/json" -H "X-CSRFToken: $(csrf)" "localhost:8000/api/$1" -d "$2"; echo; }

curl -s -c "$JAR" localhost:8000/api/lists/                       # also sets the CSRF cookie
post lists/ '{"name": "LA"}'
post lists/1/insertions/ '{"place_name": "Bestia"}'               # first place: done at once
post lists/1/insertions/ '{"place_name": "Bavel"}'                # returns insertion_id and a question
post insertions/2/answers/ '{"question_index": 0, "answer": "worse"}'
curl -s -b "$JAR" localhost:8000/api/lists/1/                     # entries with 0-10 scores
```

| Endpoint | Returns |
|---|---|
| `GET /api/lists/` | This guest's lists |
| `POST /api/lists/` `{name}` | The new list |
| `GET /api/lists/{id}/` | Entries with position, score and tier |
| `POST /api/lists/{id}/insertions/` `{place_name, city?, tier?}` | `{insertion_id, question}`, or `{insertion_id, done, position, list}` |
| `POST /api/insertions/{id}/answers/` `{question_index, answer, response_ms?}` | `{question}`, or `{done, position, list}` |
| `POST /api/insertions/{id}/abandon/` | 204 |

Sending the same answer twice repeats the response without writing anything. Conflicts return
409 with a `code`: `list_changed`, `already_ranked`, `answer_mismatch`, `question_out_of_order`
or `insertion_closed`.

## Design notes

- [`docs/WRITEUP.md`](docs/WRITEUP.md): what the results mean for a product, without the statistics.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): every design decision, with the reason and what was measured.
