# PairRank: results log

Measured numbers only. Each section names the script that produced it and the
JSONL file it wrote. Hypotheses that fail stay in the log.

## S0: the simulator agrees with an exact oracle (2026-11-06)

**Question.** Before any strategy comparison means anything, the simulator has
to be right. For binary insertion under constant noise (each answer wrong with
probability ε, independently), the exact distribution of where a restaurant
ends up can be computed without sampling: `oracle.enumerate_binary_insertion`
walks every branch of the search. The simulation (`sim/session.py` driving
`strategies/binary.py`) must reproduce it.

**Command.** `python scripts/s0_oracle_check.py` → `runs/s0_oracle.jsonl`
(10,000 insertions per cell, master seed 20261106, about 2 s on an M4 MacBook
Air). The rows record commit `e2fee6f` with uncommitted changes, because S0 was
not yet committed when it ran; rerun after committing to get a clean commit hash.

**Result: all 16 cells pass.** The largest gap between simulated and exact mean
error is 1.28 standard errors (pass: < 3), and the smallest χ² p-value for the
full error distribution is 0.094 (pass: > 0.001).

Mean |rank error| in positions (exact = the oracle; first order = ε(n + 1)/2):

| n | ε = 0.05 exact / sim | ε = 0.10 exact / sim | ε = 0.20 exact / sim | ε = 0.30 exact / sim | first order at ε = 0.10 |
|---|---|---|---|---|---|
| 9 | 0.321 / 0.311 | 0.643 / 0.658 | 1.292 / 1.287 | 1.948 / 1.968 | 0.50 |
| 19 | 0.603 / 0.605 | 1.222 / 1.219 | 2.503 / 2.546 | 3.836 / 3.858 | 1.00 |
| 49 | 1.412 / 1.426 | **2.890** / 2.933 | 6.029 / 6.071 | 9.383 / 9.437 | 2.50 |
| 99 | 2.740 / 2.644 | 5.645 / 5.685 | 11.894 / 11.802 | 18.643 / 18.677 | 5.00 |

At ε = 0.10, binary insertion places the restaurant exactly right only part of
the time, using fewer than ⌈log₂(n + 1)⌉ questions on average:

| n | exactly placed (sim) | mean questions (sim) |
|---|---|---|
| 9 | 69.4% | 3.36 |
| 19 | 62.8% | 4.35 |
| 49 | 55.3% | 5.65 |
| 99 | 49.6% | 6.63 |

**What this says.**
- The simulator is trustworthy for binary insertion under constant noise. Every
  later strategy is checked against an exact result in the same way (S1:
  posteriors against `oracle.exact_slot_posterior`).
- The first-order law ε(n + 1)/2 underestimates the exact error by 13–29% at
  ε = 0.10 (2.50 vs 2.89 at n = 49), and by more at higher ε (7.50 vs 9.38 at
  n = 49, ε = 0.30). Small intervals late in the search and stacked mistakes
  aren't in the first-order argument. **The exact value, 2.89 positions for the
  50th restaurant at 10% noise, is the baseline every other strategy is compared
  with in S1.**
- Even at 10% noise, binary insertion misplaces the 50th restaurant almost half
  the time (55.3% exact placement).

**Other S0 checks** (all in `pytest`, 100 tests, about 2.5 s):
- Two independent oracles (branch walk, and a loop over every right/wrong
  answer pattern) agree to 1e-15.
- With no noise, binary insertion is exact for n ∈ {0, 1, 2, 3, 7, 8, 49, 100},
  1,000 random insertions each, within ⌈log₂(n + 1)⌉ questions.
- The strategy state round-trips through JSON at every step of 200 random
  insertions.
- Bradley–Terry noise calibrated to ε ∈ {0.05, 0.1, 0.2, 0.3} gives an
  empirical error rate within ±0.002 of the target on 10⁶ fresh pairs.
- `kendall_tau_bruteforce` matches SciPy on 1,000 random permutations.
