# Decisions

One row per decision: date, choice, why, what was measured.

| Date | Decision | Why |
|---|---|---|
| 2026-11-05 | Repo `pair-rank`; Python package `pairrank` | Package names can't contain hyphens |
| 2026-11-05 | No data from real people; every experiment uses simulated users | Only simulated users have a known true ranking; everything runs on one machine |
| 2026-11-05 | A/B test also run through the app with simulated HTTP traffic | Tests assignment, logging and SQL end to end, which an offline simulation can't |
| 2026-11-05 | Angular front end | Beli's stack |
| 2026-11-05 | Django 5.2 LTS + Django REST Framework | Supported to April 2028; no version chasing |
| 2026-11-05 | One repo for the app and the analysis | The app imports the evaluated strategies; one CI proves they match |
| 2026-11-05 | Positions stored, scores computed on read | No stored score can drift out of sync |
| 2026-11-05 | Contiguous integer positions, not fractional keys | Lists are small; SQL analytics stay simple |
| 2026-11-05 | Render web service + Neon Postgres; Angular served by Django/WhiteNoise | One origin (no CORS, simpler CSRF); free tiers to be verified at A3 |
| 2026-11-05 | Guest users, no accounts | No passwords to store |
| 2026-11-05 | Postgres in all backend tests (no SQLite) | Deferred constraints and row locks differ on SQLite |
| 2026-11-05 | Q4 experiments resample a bank of simulated users | 2,000 full experiments in plain Python would take hours; simulated users are i.i.d. |
| 2026-11-09 | Looker Studio or Tableau Public for the dashboard, from a CSV of SQL results (replaces Metabase) | The DS posting names Tableau and Looker; a CSV needs no cloud-reachable database |
| 2026-11-09 | SQL is primary for metrics and required before applying; pandas checks it; pandas and matplotlib build every table and figure | Puts the tools the postings name to real use |
| 2026-11-05 | Free-text places + a hand-typed LA seed list | No external API or data license needed |
| 2026-11-06 | Python 3.14 for everything (3.13 also in CI) | A0 wheel check on the M4 (macOS 26.2, Python 3.14.6): every pinned package installed from wheels (numpy 2.5.4, scipy 1.18.1, pandas 3.1.1, matplotlib 3.11.2, statsmodels 0.15.0, django 5.2.19, djangorestframework 3.18.3, psycopg 3.3.8 with the binary implementation, gunicorn 26.2.0, whitenoise 6.12.0, httpx 0.28.1); `django.setup()` with DRF raised no DeprecationWarning. No fallback to 3.13 needed |
| 2026-11-06 | Strategy state is the transcript (list size, answers, seed); strategies recompute everything else | Round-trips through JSON exactly, so the app can store it as-is and replay is trivial; recomputation costs O(questions) per step, negligible |
| 2026-11-06 | Two independent exact oracles for binary insertion (branch walk + answer-pattern loop) | An oracle that shares code with the thing it checks proves nothing; they agree to 1e-15 |
| 2026-11-09 | Bisection and `verify` budget 4⌈log₂(n + 1)⌉ questions, not the design doc's 2⌈log₂(n + 1)⌉ | 2L = 12 at n = 49 barely clears the 10.6-question information floor, so the budget, not the stopping rule, would decide accuracy. Measured max over the grid: 28 for bisection and 30 for `verify`, both at n = 99 |
| 2026-11-09 | Bisection asks where the posterior split is closest to 50/50 | "First position past half" got stuck and misplaced with no noise; found by the ε = 0 test (RESULTS.md) |
| 2026-11-09 | Q1 calibrates BT temperature on differences of i.i.d. N(0, 1) utilities | Q1's lists use those utilities; only the ratio of utility gaps to T matters |
| 2026-11-09 | App default strategy: Bayesian bisection (δ = 0.1), behind a one-line setting | Lowest error in Q1 and Q4 under constant and BT noise. Costs about twice the questions; a real product would likely loosen the stopping rule (δ = 0.3: 0.65 positions in 8.3 questions at n = 49) and should test it |
| 2026-11-09 | Q4 tests bisection as well as the pre-registered `verify` | Q1 showed bisection is what you'd ship; the original `verify` arm stays in the results |
| 2026-11-09 | Power checks scale the effect with a treated fraction | The full effect needs only a handful of users, where the normal approximation isn't meaningful; real experiments hunt for small effects |
| 2026-11-09 | Per-user error rate capped at 0.49 in the mixed-user bank | Beta(2, 18) has a rare tail above 0.5, where the noise model is undefined; at least one of the 50,000 users hit it |
| 2026-11-09 | `RankList.owner` and `Place.created_by` point at Django's user table; a guest is a user row with no password | Keeps "one browser = one guest" without a second identity table; seeded places have no creator, so `created_by` is nullable |
| 2026-11-09 | Allowed values (status, answer, tier), trimmed names and "done means it has a result" are also database checks | The SQL analysis reads these tables directly, and simulated faulty clients shouldn't be able to write a state the funnel can't count |
| 2026-11-09 | `DATABASE_URL` parsed by a 12-line function, tested | One format to support; not worth a dependency |
| 2026-11-09 | Backend tests have their own `backend/pytest.ini`; mypy strict stays on `src/pairrank` | The simulation suite must keep running without Django (macOS CI job). Strict typing the Django layer would need django-stubs, not added |
| 2026-11-06 | Build backend hatchling; plain `venv` + pip, versions pinned with `==` in `pyproject.toml` | `uv` isn't installed and isn't needed at this size |
