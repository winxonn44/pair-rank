# Conventions

Written before any simulation code (checkpoint S0). Every convention here has a
test; the test file is named next to each one. Most bugs in this kind of code
are convention bugs: an off-by-one slot, or a flipped answer.

## Lists and positions

- **Positions are 0-indexed, and 0 is the best entry.** Display rank =
  position + 1. (`tests/test_conventions.py`)
- **Slots.** Inserting into a list of n entries has n + 1 slots, r ∈ {0, …, n}.
  Slot r means "goes immediately before the entry currently at position r";
  r = n means last. Inserting into an empty list gives slot 0.
  (`tests/test_conventions.py`, `tests/test_binary.py`)
- **True slot.** For a new place with true utility u, its true slot is the
  number of entries in the current list with true utility greater than u. Rank
  error is |placed slot − true slot|, in positions. (`tests/test_session.py`)

## Questions and answers

- A question names one entry by its position j: "is the new place better than
  the entry at position j?"
- `new_is_better = True` means the user says the new place wins.
- A correct `True` implies the true slot is ≤ j; a correct `False` implies it's
  > j. (`tests/test_conventions.py`)
- Utilities are continuous, so exact ties have probability zero. If one happens,
  the new place counts as *not* better (strict `>`).

## Scores

- 10 is best and 0 is worst. Scores are floats internally and are rounded to
  one decimal **only for display**. (`tests/test_conventions.py`)
- **Percentile mapping:** s = 10(n − 1 − p)/(n − 1) for position p of n ≥ 2; a
  single entry scores 10. (`tests/test_scoring.py`)
- **Tiered mapping:** within a tier of m entries, position q scores
  lo + (hi − lo)(m − q − 0.5)/m (mid-ranks, so tiers never collide and a lone
  entry sits mid-band). (`tests/test_scoring.py`)
- **True score:** 10 × the place's true quantile among the user's possible places.
- Tier bands for the tiered mapping: `disliked` [0, 10/3), `fine` [10/3, 20/3),
  `liked` [20/3, 10]. (`tests/test_conventions.py`)

## Simulated users

- Restaurant j has global quality g_j ~ N(0, 1) and factors b_j ~ N(0, I_k);
  user u has taste a_u ~ N(0, I_k / k), with k = 8. True utility is
  U_uj = g_j + a_u · b_j, so Var(U) = 2. (`tests/test_users.py`)
- For Q1, a single insertion only needs n + 1 i.i.d. utilities: the true slot is
  then uniform on {0, …, n}, which is what the exact oracle assumes.

## Noise models

- **M-const:** each answer is wrong with probability ε, independently.
- **M-BT:** P(the user says the new place is better) = σ((u_new − u_ref) / T).
  T is calibrated so the average error over random within-user pairs of the
  simulated population equals the target ε. (`tests/test_noise.py`: the
  empirical error rate over 10⁶ fresh answers is within ±0.002 of the target.)
- **M-sticky:** wraps another model. If the same pair of places was asked
  before, the earlier answer repeats with probability ρ; otherwise a fresh
  answer is drawn. One instance per simulated user, because it remembers.
  (`tests/test_noise.py`)
- Note: the average error over *random* pairs is not the error rate a search
  sees. Searches ask about close pairs more often, so under M-BT the realized
  error rate during insertion is higher. S1 measured it: 22% of asked questions
  at a calibrated 10%. Q1 calibrates T on differences of its i.i.d. N(0, 1) utilities.

## Randomness

- One `numpy.random.SeedSequence(master_seed)` per script; independent streams
  via `.spawn()`; the `PCG64` bit generator. Never Python's `random` module or
  NumPy's global state.
- NumPy guarantees `Generator` streams only within a version, so every results
  row records the NumPy version, the master seed and the git commit
  (`pairrank.io.run_metadata`).

## Strategy state

- A strategy's state is the transcript: the list size, the answers so far
  (position asked, answer) and a seed. Each strategy recomputes everything else
  from the transcript, so the state round-trips through JSON exactly, and the
  app can store it as-is. (`tests/test_binary.py`)
