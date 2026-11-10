# What this means for a product that ranks by comparison

*Draft. Every number comes from simulated users with known true preferences, and no real
person's answers were used. The numbers and the commands that regenerate them are in
[`RESULTS.md`](RESULTS.md).*

## The short version

Asking "better or worse?" is a good way to rank things people care about, but a plain binary
search trusts every answer. When people answer wrongly 10% of the time, one early mistake sends
a restaurant to the wrong part of the list and nothing ever corrects it. A smarter question
strategy fixes most of that, at the cost of about twice as many questions. Whether that trade
is worth it can only be settled by an experiment with real users, and this project works out
how to run that experiment properly.

## How many questions to ask

With a list of 49 restaurants and 10% wrong answers, binary insertion asks 5.6 questions and
puts the new place 2.88 positions away from where it belongs, on average. A Bayesian strategy
that keeps asking until it's confident gets that down to 0.20 positions, using 10.9 questions.
Loosening its stopping rule gives 0.65 positions in 8.3 questions, which is probably closer to
what a product should ship.

The gain depends on how people make mistakes. It shrinks when mistakes concentrate on places
that are close in quality, and when someone repeats the same wrong answer. Re-asking the exact
same pair is the option most exposed to repeated mistakes: it loses 92% of its benefit when
wrong answers stick, while asking about a neighboring place instead loses 16%.

Extra questions have a price. If 1% of people quit at each question (an assumption, not a
measurement), completion falls from 94.8% to 90.3%.

## Why scores move

If a score is a percentile of someone's list, it has to change as the list grows, even when
every answer was right. A restaurant's score moves about 0.94 points on a 0–10 scale as a list
grows from 10 to 50 places, and adding one new place visibly changes about 60% of the displayed
scores. Better questions can't fix this, because the movement comes from the list growing and
not from mistakes.

Sorting places into three tiers first roughly halves the drift and cuts visible changes to 19%.
That result assumes people always pick the right tier, so it flatters tiers somewhat.

## What to A/B test

Test the question strategy against binary insertion, with completion as a guardrail.

- **Sample size.** 481 users per arm detect a 0.25-position improvement at 80% power. The
  formula was checked with 2,000 simulated experiments.
- **Unit of analysis.** Use the user, not the insertion. One person's insertions aren't
  independent, and later ones sit on earlier mistakes.
- **Don't peek.** Stopping at the first significant result across five looks gives a 14.9%
  false-positive rate instead of 5%.
- **The hard part.** In a real product nobody knows the true ranking, so placement error can't
  be measured directly. An occasional audit question ("which of these two is better?") can stand
  in for it, but one audit per user barely tracks true error (r = 0.22). It takes about 20 to
  reach r = 0.68, so audits are better for comparing groups than for judging individuals.

## A metric to be careful with

A contradiction rate looks like a good consistency measure, but it isn't one. Binary search
shows 0% contradictions because it never asks a question that could expose one, and it's the
least accurate strategy tested. The strategies that catch mistakes show 48–67%, because
asking more means finding more. Any dashboard tracking contradictions should say so.

## What this doesn't show

Nothing here measures how real people answer. The 10% error rate, the shape of the noise and the
quit rate are all assumptions. What the simulations can show is which conclusions hold up across
those assumptions, and what a real experiment would need in order to be trustworthy.
