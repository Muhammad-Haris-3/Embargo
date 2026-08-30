"""The knowability guard, attacked.

A guard that is never made to fire is a guard nobody has tested. Each case
below is an attempt to smuggle a value from the future into a point-in-time
computation, and each one must raise rather than return something plausible.
"""

from __future__ import annotations

import datetime as dt

import pytest

from embargo.knowability import AsOf, NotKnowable

D = dt.date(2020, 6, 30)


class TestKnows:
    def test_earlier_is_knowable(self):
        assert AsOf(D).knows(dt.date(2020, 1, 1))

    def test_the_as_of_date_itself_is_knowable(self):
        """Inclusive on purpose. A record posted on D was readable on D."""
        assert AsOf(D).knows(D)

    def test_one_day_later_is_not(self):
        assert not AsOf(D).knows(D + dt.timedelta(days=1))

    def test_absent_carries_no_information_from_the_future(self):
        """A missing value is missing, not futuristic.

        Treating None as unknowable would make every unposted trial raise, and
        unposted trials are the population this project is about.
        """
        assert AsOf(D).knows(None)


class TestRequire:
    def test_returns_a_knowable_date(self):
        assert AsOf(D).require(dt.date(2019, 1, 1), "submit") == dt.date(2019, 1, 1)

    def test_raises_on_a_future_date(self):
        with pytest.raises(NotKnowable) as exc:
            AsOf(D).require(dt.date(2021, 1, 1), "results_first_post")
        assert "results_first_post" in str(exc.value)
        assert "2020-06-30" in str(exc.value)

    def test_the_message_names_what_leaked(self):
        """A guard that raises without saying what leaked sends the reader
        hunting through the call stack for a date."""
        with pytest.raises(NotKnowable, match="primary completion"):
            AsOf(D).require(dt.date(2025, 1, 1), "primary completion date")


class TestObservable:
    def records(self):
        return [
            {"nct_id": "A", "results_first_post": dt.date(2019, 1, 1)},
            {"nct_id": "B", "results_first_post": D},
            {"nct_id": "C", "results_first_post": dt.date(2020, 7, 1)},
            {"nct_id": "D", "results_first_post": None},
        ]

    def test_only_records_posted_by_the_date(self):
        seen = [r["nct_id"] for r in AsOf(D).observable(self.records())]
        assert seen == ["A", "B"]

    def test_a_record_posted_after_the_date_is_invisible(self):
        """C posted the next day. On D it was indistinguishable from a trial
        that had submitted nothing, and its submission date was not disclosed
        until it posted."""
        assert "C" not in [r["nct_id"] for r in AsOf(D).observable(self.records())]

    def test_an_unposted_record_is_invisible(self):
        """The premise of the project, enforced in code.

        D has never posted. It is exactly the thing that cannot be counted, and
        including it here would make the queue observable by accident.
        """
        assert "D" not in [r["nct_id"] for r in AsOf(D).observable(self.records())]

    def test_the_full_set_is_visible_from_today(self):
        """The same records, from a later vantage point, disclose more.

        This is the whole mechanism Gate 3 relies on: the truth arrives later.
        """
        later = AsOf(dt.date(2026, 1, 1))
        assert [r["nct_id"] for r in later.observable(self.records())] == ["A", "B", "C"]


class TestElapsed:
    def test_counts_whole_days(self):
        assert AsOf(D).elapsed(dt.date(2020, 6, 1)) == 29

    def test_refuses_to_measure_from_the_future(self):
        """A negative elapsed time is the arithmetic of a leak."""
        with pytest.raises(NotKnowable):
            AsOf(D).elapsed(dt.date(2021, 1, 1))
