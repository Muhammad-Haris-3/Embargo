"""Estimating a queue that cannot be observed.

The problem, stated precisely.

On date `D` we can see every trial whose results have posted, and for each one
we know when it was submitted and when it posted. We cannot see a single trial
that submitted and has not yet posted. We want the number of those.

Write `N(s)` for the number of trials submitted on day `s`. It is unknown. What
is observable on `D` is only the part of that day's cohort which has already
posted:

    O(s, D) = N(s) * F(D - s)

where `F` is the distribution function of the wait. Rearranging gives the
estimator this module implements:

    Qhat(D) = sum over observed trials i of  (1 - F(T_i)) / F(T_i)

with `T_i = D - submit_i`, the time that trial had available to post in. Each
observed trial stands for `1 / F(T_i)` actual submissions from its slice of the
cohort, of which a fraction `1 - F(T_i)` are still waiting. This is the standard
reverse-time inflation used for reporting delay, and it needs `F`.

**`F` cannot simply be counted either.** The waits visible on `D` are
right-truncated: a trial submitted at `s` can only show a wait of `w` if
`s + w <= D`. Long waits are systematically missing, and the deeper the
truncation the more they are missing. Averaging what is visible would produce a
wait distribution that is too fast, which would then produce a queue that is too
small -- the error compounds in the direction that makes the finding look
smaller.

`lynden_bell` is the non-parametric maximum-likelihood estimator for exactly
this: right-truncated observations, no distributional assumption. It is the
reverse-time analogue of Kaplan-Meier.

**What it assumes**, stated here because it is the load-bearing assumption of
the whole project and it is not testable from the data alone:

    the wait distribution does not depend on when a trial was submitted

If review got dramatically slower in 2023, a `F` estimated across all cohorts
misstates 2023. Gate 3 is what puts a number on how wrong this is, by marking
the estimator against dates whose answer has since been disclosed.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    """One trial that has posted, seen from a vantage point.

    `wait` is what it took. `available` is how long it had -- the days between
    submission and the vantage date. `wait <= available` always holds, and that
    inequality is the truncation.
    """

    wait: int
    available: int


class StepCDF:
    """A right-continuous step function, evaluated by binary search."""

    def __init__(self, xs: list[int], fs: list[float]) -> None:
        self.xs = xs
        self.fs = fs

    def __call__(self, t: float) -> float:
        if not self.xs or t < self.xs[0]:
            # No observed wait is this short. The estimator has nothing to say
            # about a trial this recent, and says zero rather than guessing.
            return 0.0
        i = bisect.bisect_right(self.xs, t) - 1
        return self.fs[i]

    @property
    def support(self) -> tuple[int, int] | None:
        return (self.xs[0], self.xs[-1]) if self.xs else None


def lynden_bell(observations: list[Observation]) -> StepCDF:
    """The wait distribution, corrected for right truncation.

    For each distinct observed wait `x`, the reverse risk set is

        R(x) = #{ j : wait_j <= x <= available_j }

    which counts the trials that *could* have shown a wait of `x` and are
    comparable at that point. Because `wait_j <= available_j` always holds, this
    simplifies to a difference of two counts:

        R(x) = #{ j : wait_j <= x }  -  #{ j : available_j < x }

    and both sides are one binary search over a sorted array. Computing R
    directly by scanning every observation for every distinct wait is the
    obvious implementation and is quadratic; on 75,000 observations with 5,000
    distinct waits it does not finish.
    """
    if not observations:
        return StepCDF([], [])

    waits = sorted(o.wait for o in observations)
    availables = sorted(o.available for o in observations)

    distinct: list[int] = []
    counts: list[int] = []
    for w in waits:
        if distinct and distinct[-1] == w:
            counts[-1] += 1
        else:
            distinct.append(w)
            counts.append(1)

    # Walk from the longest wait down, accumulating the product. F at the
    # longest observed wait is 1: everything is at most the maximum.
    fs = [0.0] * len(distinct)
    product = 1.0
    for i in range(len(distinct) - 1, -1, -1):
        fs[i] = product
        x = distinct[i]
        at_most_x = bisect.bisect_right(waits, x)
        available_before_x = bisect.bisect_left(availables, x)
        risk = at_most_x - available_before_x
        if risk > 0:
            product *= 1.0 - counts[i] / risk

    return StepCDF(distinct, fs)


@dataclass(frozen=True)
class QueueEstimate:
    q_hat: float
    n_observed: int
    n_usable: int
    n_below_floor: int
    floor: float
    inflation_max: float

    @property
    def excluded_share(self) -> float:
        return self.n_below_floor / self.n_observed if self.n_observed else 0.0


def estimate_queue(
    observations: list[Observation],
    cdf: StepCDF | None = None,
    *,
    floor: float = 0.05,
) -> QueueEstimate:
    """The number of trials that had submitted and not yet posted.

    `floor` is a guard, and it biases the answer in a direction that has to be
    stated. A trial submitted days before the vantage date has had almost no
    time to post, so `F(T)` is near zero and `1/F(T)` explodes -- one such
    observation would stand for thousands of submissions on the strength of
    nothing. Observations below the floor are dropped.

    **The consequence is that `Qhat` undercounts the freshest part of the
    queue**, which is also the part most likely to still be in it. `Qhat` is
    therefore a lower bound too, and both bounds are reported rather than
    reconciled. The share dropped is returned so the size of the omission is
    visible beside the number it affects.
    """
    if not observations:
        return QueueEstimate(0.0, 0, 0, 0, floor, 0.0)

    cdf = cdf or lynden_bell(observations)
    total = 0.0
    usable = 0
    below = 0
    worst = 0.0

    for o in observations:
        f = cdf(o.available)
        if f < floor:
            below += 1
            continue
        inflation = (1.0 - f) / f
        worst = max(worst, inflation)
        total += inflation
        usable += 1

    return QueueEstimate(
        q_hat=total,
        n_observed=len(observations),
        n_usable=usable,
        n_below_floor=below,
        floor=floor,
        inflation_max=worst,
    )
