"""Cohort construction, offline.

The arithmetic here decides a published number, and every case below is one
where getting it wrong would move that number in a direction someone might
prefer.
"""

from __future__ import annotations

import datetime as dt

from embargo.preregistration import MATURITY_DAYS
from embargo.waits import Cohort, build_cohorts


def record(submit: str | None, post: str | None, partial: bool = False) -> dict:
    return {
        "results_first_submit": dt.date.fromisoformat(submit) if submit else None,
        "results_first_post": dt.date.fromisoformat(post) if post else None,
        "has_partial_date": partial,
    }


class TestBuildCohorts:
    def test_grouped_by_submission_not_posting(self):
        """The whole point of cohorts.

        Grouping by posting year is what made the M0 probe biased: it selects
        on the very thing being measured.
        """
        cohorts = build_cohorts(
            [
                record("2015-01-01", "2016-06-01"),  # submitted 2015, posted 2016
                record("2015-12-31", "2019-01-01"),  # submitted 2015, posted 2019
            ]
        )
        assert set(cohorts) == {2015}
        assert sorted(cohorts[2015].waits) == [517, 1097]

    def test_negative_wait_is_excluded_and_counted(self):
        cohorts = build_cohorts([record("2015-06-01", "2015-05-01")])
        assert cohorts[2015].waits == []
        assert cohorts[2015].negative == 1

    def test_negative_wait_is_not_clamped_to_zero(self):
        """A clamp would pull the median down by exactly as many rows as there
        are broken records, which is a finding about our arithmetic."""
        cohorts = build_cohorts(
            [record("2015-01-01", "2015-01-11"), record("2015-06-01", "2015-05-01")]
        )
        assert cohorts[2015].waits == [10]

    def test_unposted_record_joins_the_cohort_but_contributes_no_wait(self):
        cohorts = build_cohorts([record("2015-03-01", None)])
        assert cohorts[2015].waits == []
        assert cohorts[2015].negative == 0

    def test_record_without_a_submit_date_is_skipped(self):
        assert build_cohorts([record(None, "2016-01-01")]) == {}

    def test_partial_dates_are_counted(self):
        cohorts = build_cohorts([record("2015-01-01", "2015-01-11", partial=True)])
        assert cohorts[2015].partial == 1

    def test_same_day_post_is_a_zero_wait_not_a_missing_one(self):
        cohorts = build_cohorts([record("2015-01-01", "2015-01-01")])
        assert cohorts[2015].waits == [0]


class TestMaturity:
    def test_measured_from_the_end_of_the_cohort_year(self):
        """A trial submitted in December had the least time of anyone in its
        cohort, so maturity is measured from 31 December or it would call a
        cohort resolved while part of it still could not have resolved."""
        cohort = Cohort(year=2015, waits=[10])
        just_mature = dt.date(2015, 12, 31) + dt.timedelta(days=MATURITY_DAYS)
        assert cohort.summary(just_mature)["is_mature"] is True
        assert cohort.summary(just_mature - dt.timedelta(days=1))["is_mature"] is False

    def test_immature_cohorts_are_not_quotable(self):
        cohort = Cohort(year=2024, waits=[10, 20, 30])
        summary = cohort.summary(dt.date(2026, 8, 30))
        assert summary["is_mature"] is False
        assert summary["quotable"] is False

    def test_n_is_always_a_lower_bound(self):
        """Trials still in review cannot be seen, so the cohort size is never
        known -- only the part of it that has emerged."""
        assert Cohort(year=2015, waits=[1]).summary(dt.date(2026, 8, 30))["n_is_lower_bound"]


class TestPercentiles:
    def test_median_of_a_known_set(self):
        assert Cohort(year=2015, waits=[1, 2, 3, 4, 5]).percentile(0.50) == 3

    def test_empty_cohort_has_no_percentile(self):
        assert Cohort(year=2015).percentile(0.50) is None

    def test_percentile_does_not_run_off_the_end(self):
        assert Cohort(year=2015, waits=[7]).percentile(0.99) == 7

    def test_summary_of_an_empty_cohort_does_not_divide_by_zero(self):
        summary = Cohort(year=2015).summary(dt.date(2026, 8, 30))
        assert summary["n_observed"] == 0
        assert summary["share_over_365d"] is None
