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
| 2026-11-05 | Metabase (Docker) for the dashboard | Works against local Postgres |
| 2026-11-05 | Free-text places + a hand-typed LA seed list | No external API or data license needed |
| 2026-11-06 | Python 3.14 for everything (3.13 also in CI) | A0 wheel check on the M4 (macOS 26.2, Python 3.14.6): every pinned package installed from wheels (numpy 2.5.4, scipy 1.18.1, pandas 3.1.1, matplotlib 3.11.2, statsmodels 0.15.0, django 5.2.19, djangorestframework 3.18.3, psycopg 3.3.8 with the binary implementation, gunicorn 26.2.0, whitenoise 6.12.0, httpx 0.28.1); `django.setup()` with DRF raised no DeprecationWarning. No fallback to 3.13 needed |
| 2026-11-06 | Strategy state is the transcript (list size, answers, seed); strategies recompute everything else | Round-trips through JSON exactly, so the app can store it as-is and replay is trivial; recomputation costs O(questions) per step, negligible |
| 2026-11-06 | Two independent exact oracles for binary insertion (branch walk + answer-pattern loop) | An oracle that shares code with the thing it checks proves nothing; they agree to 1e-15 |
| 2026-11-06 | Build backend hatchling; plain `venv` + pip, versions pinned with `==` in `pyproject.toml` | `uv` isn't installed and isn't needed at this size |
