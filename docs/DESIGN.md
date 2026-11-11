# Design

How PairRank is put together and why. Results are in [`RESULTS.md`](RESULTS.md), the reasoning
behind each choice is in [`DECISIONS.md`](DECISIONS.md), and the definitions every test relies
on are in [`conventions.md`](conventions.md).

## The question

A user adds a restaurant to a ranked list by answering "is it better or worse than this one?".
People answer inconsistently, so two things need measuring: how many questions it takes to put
the restaurant in the right place, and how much the 0–10 scores derived from positions move as
a list grows. Only simulated users have a known true ranking, so every experiment uses them.
No data comes from real people.

## Two parts, one codebase

| Part | What it is | Where |
|---|---|---|
| Simulation | Simulated users, noise models, placement strategies, exact oracles, metrics and the A/B-test simulator | `src/pairrank/`, `scripts/`, `runs/` |
| App | A Django REST API on PostgreSQL and an Angular page that runs the same strategies | `backend/`, `frontend/` |
| Analysis | SQL metrics on the app's schema, checked against pandas | `sql/`, `scripts/load_sim_to_pg.py` |

The app imports the strategies from the simulation package rather than reimplementing them, so
one CI run shows that what was evaluated is what runs.

## Placement strategies

Every strategy has the same three-method interface: `start(n, seed)`, `next_query(state)`,
which returns either a position to ask about or a final slot, and `observe(state, position,
new_is_better)`. Its whole state is the transcript of answers so far (`InsertionState`), which
serializes to JSON. The app stores that JSON on the insertion row and replays it on each
request, so the server holds no strategy objects between requests.

| Strategy | Idea |
|---|---|
| `binary` | Binary insertion. About log₂(n + 1) questions; trusts every answer |
| `majority` | Ask each question twice, a third time if the answers disagree |
| `majority-neighbor` | As above, but re-ask using a neighboring entry |
| `bisection` | Bayesian bisection: a posterior over slots, ask at its median, stop when confident |
| `verify` | Binary insertion, then check the neighbors; fall back to bisection on a contradiction |

The app runs `bisection`.

## Data model

| Table | Holds | Key constraints |
|---|---|---|
| `ranking_place` | A restaurant name and city | Unique per city, ignoring case in the name |
| `ranking_ranklist` | One guest's list and its `version` | |
| `ranking_listentry` | A place at a position | `UNIQUE(list, position)` deferred to commit; `UNIQUE(list, place)` |
| `ranking_insertion` | One attempt to add a place: strategy, transcript, status | Status is open, done or abandoned |
| `ranking_comparison` | One answered question | Unique per insertion and question index |

Positions are stored as contiguous integers, with 0 as the best entry. Scores are never stored:
they're computed from positions on every read, so a stored score can't go stale. Inserting at
position k shifts every entry below it down by one, which only works inside one transaction
because the uniqueness check on position is deferred until commit.

## Correctness under concurrency

Finishing an insertion locks the insertion and its list together (`select_for_update`). If the
list's version changed since the insertion started, for example because another tab finished
first, the request fails with a 409 `list_changed` instead of writing into a list it didn't see.
Answers are idempotent by question index, so a double-click repeats the first response and
writes nothing.

## The page

The Angular page has three components: `rank-page` holds the state, `question-card` asks the
question and accepts ← for better and → for worse, and `ranked-list` shows the list and
highlights the entry being compared against. Django serves the built page with WhiteNoise from
the same origin as the API, which avoids CORS and lets Angular send Django's CSRF header. Guests
need no account: the first write creates one, tied to the session cookie.

## Testing

- **Exact oracles.** The simulator's distribution of placement error matches exact enumeration
  and brute-force Bayes before any result is reported.
- **Replay.** 1,080 simulated transcripts replayed through the API give the same questions and
  final positions as the simulator.
- **Concurrency and query counts.** Two tabs racing to finish always give one success and one
  409, and starting, answering and reading a list each have a fixed upper bound on SQL queries.
- **SQL against pandas.** Every SQL metric must equal an independent pandas version.
- **Frontend.** Unit tests for each component and the API client, and a scripted run in Chrome that
  ranked 10 places from an empty list before this release.

Tests were checked by breaking the code on purpose and confirming that they fail. CI runs all of
it on Linux with PostgreSQL 17, and the simulation tests on macOS too.

## Not yet built

Deployment, the end-to-end A/B test driven through the app with simulated traffic, a TypeScript
port of the strategies, and tiers that change the score.
