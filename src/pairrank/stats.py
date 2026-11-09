"""Small statistical helpers used to compare simulations with exact results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from scipy import stats as sps


def chi2_against_pmf(
    samples: Sequence[int], pmf: Mapping[int, float], min_expected: float = 5.0
) -> tuple[float, int, float]:
    """Pearson chi-square of integer samples against an exact pmf.

    Bins are pooled from both tails inward until every bin's expected count is at
    least `min_expected`. Returns (statistic, degrees of freedom, p-value).
    """
    n = len(samples)
    keys = sorted(pmf)
    if any(s not in pmf for s in set(samples)):
        raise ValueError("a sample has probability zero under the pmf")
    counts = {k: 0 for k in keys}
    for s in samples:
        counts[s] += 1
    exp = [pmf[k] * n for k in keys]
    obs = [float(counts[k]) for k in keys]

    def pool(e: list[float], o: list[float]) -> tuple[list[float], list[float]]:
        out_e: list[float] = []
        out_o: list[float] = []
        acc_e = acc_o = 0.0
        for ei, oi in zip(e, o, strict=True):
            acc_e += ei
            acc_o += oi
            if acc_e >= min_expected:
                out_e.append(acc_e)
                out_o.append(acc_o)
                acc_e = acc_o = 0.0
        if acc_e > 0 and out_e:
            out_e[-1] += acc_e
            out_o[-1] += acc_o
        return out_e, out_o

    exp, obs = pool(exp, obs)
    if len(exp) < 2:
        return 0.0, 0, 1.0
    total = sum(exp)
    exp = [e * n / total for e in exp]  # absorb float rounding so the sums match
    result = sps.chisquare(np.asarray(obs), np.asarray(exp))
    return float(result.statistic), len(exp) - 1, float(result.pvalue)
