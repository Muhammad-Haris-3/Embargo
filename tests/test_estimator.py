"""The estimator, against simulated worlds where the answer is known.

Gate 3 marks the estimator against real dates whose answer has since been
disclosed. That is the real test and it happens against live data. These are
the test that has to pass first: on data generated from a distribution chosen
here, with a queue counted here, does the estimator recover the number?

A simulation is not proof that the method works on the registry. It is proof
that the implementation computes the method, which is a different claim and the
one that fails silently.
"""

from __future__ import annotations

import itertools
import math
import random

import pytest

from embargo.estimator import (
    Observation,
    QueueEstimate,
    estimate_queue,
    lynden_bell,
)


def simulate(
    *,
    n_per_day: int = 40,
    days: int = 4000,
    vantage: int | None = None,
    seed: int = 7,
    mean_wait: float = 120.0,
) -> tuple[list[Observation], int, int]:
    """A world with a known queue.

    Trials are submitted at a steady rate over `days`. Each waits a
    geometrically distributed number of days. At the vantage date we count what
    is observable, and separately count the truth.

    Returns (observations, true_queue, submitted_by_vantage).
    """
    rng = random.Random(seed)
    vantage = days if vantage is None else vantage

    observations: list[Observation] = []
    true_queue = 0
    submitted = 0

    p = 1.0 / mean_wait
    for s in range(days):
        if s > vantage:
            break
        for _ in range(n_per_day):
            submitted += 1
            wait = _geom(rng, p)
            post = s + wait
            if post <= vantage:
                observations.append(Observation(wait=wait, available=vantage - s))
            else:
                true_queue += 1
    return observations, true_queue, submitted


def _geom(rng: random.Random, p: float) -> int:
    """Number of days until posting, minimum 1."""
    u = rng.random()
    return max(1, math.ceil(math.log(1.0 - u) / math.log(1.0 - p)))


class TestLyndenBell:
    def test_recovers_a_known_distribution_under_truncation(self):
        """The whole point: naive counting is biased, this is not.

        Under right truncation the visible waits are too short. If the corrected
        CDF were no better than the empirical one, there would be no reason to
        implement it.
        """
        obs, _, _ = simulate(days=3000, vantage=3000, mean_wait=150.0)
        cdf = lynden_bell(obs)

        # True geometric CDF at the mean: 1 - (1-p)^x, p = 1/150
        true_at_150 = 1.0 - (1.0 - 1 / 150.0) ** 150
        assert cdf(150) == pytest.approx(true_at_150, abs=0.05)

    def test_is_monotone_non_decreasing(self):
        obs, _, _ = simulate(days=1500, vantage=1500)
        cdf = lynden_bell(obs)
        values = [cdf(t) for t in range(0, 1200, 10)]
        assert all(b >= a - 1e-9 for a, b in itertools.pairwise(values))

    def test_reaches_one_at_the_longest_observed_wait(self):
        obs, _, _ = simulate(days=1200, vantage=1200)
        cdf = lynden_bell(obs)
        assert cdf(cdf.support[1]) == pytest.approx(1.0)

    def test_is_zero_below_the_shortest_observed_wait(self):
        """The estimator says nothing rather than guessing, and the caller's
        floor is what turns that into a documented exclusion."""
        cdf = lynden_bell([Observation(wait=10, available=100)])
        assert cdf(9) == 0.0

    def test_empty_input_is_not_an_error(self):
        cdf = lynden_bell([])
        assert cdf(100) == 0.0
        assert cdf.support is None


class TestEstimateQueue:
    def test_recovers_a_known_queue(self):
        """The claim M4 rests on, on data where the truth is countable."""
        obs, true_queue, _ = simulate(days=4000, vantage=4000, mean_wait=120.0)
        estimate = estimate_queue(obs)
        assert estimate.q_hat == pytest.approx(true_queue, rel=0.15)

    def test_recovers_a_known_queue_at_a_second_rate(self):
        obs, true_queue, _ = simulate(days=4000, vantage=4000, mean_wait=300.0, seed=11)
        estimate = estimate_queue(obs)
        assert estimate.q_hat == pytest.approx(true_queue, rel=0.15)

    def test_the_naive_count_is_not_a_substitute(self):
        """Observing zero pending trials is what the registry shows, and the
        queue is not zero. If this ever passed by accident the estimator would
        be unnecessary."""
        _, true_queue, _ = simulate(days=4000, vantage=4000)
        assert true_queue > 0

    def test_undercounts_rather_than_explodes_on_fresh_submissions(self):
        """The floor is a documented bias, not a silent one.

        A trial submitted days before the vantage date has F(T) near zero, and
        1/F would let one observation stand for thousands. The floor drops it,
        which biases Qhat downward, and the share dropped is reported.
        """
        obs, _, _ = simulate(days=400, vantage=400, mean_wait=300.0)
        estimate = estimate_queue(obs, floor=0.05)
        assert estimate.n_below_floor > 0
        assert 0.0 < estimate.excluded_share < 1.0
        assert estimate.inflation_max < 1.0 / 0.05

    def test_a_lower_floor_admits_more_and_inflates_more(self):
        obs, _, _ = simulate(days=800, vantage=800, mean_wait=200.0)
        strict = estimate_queue(obs, floor=0.20)
        loose = estimate_queue(obs, floor=0.02)
        assert loose.n_usable >= strict.n_usable
        assert loose.inflation_max >= strict.inflation_max

    def test_empty_input_estimates_nothing(self):
        estimate = estimate_queue([])
        assert isinstance(estimate, QueueEstimate)
        assert estimate.q_hat == 0.0
        assert estimate.excluded_share == 0.0
