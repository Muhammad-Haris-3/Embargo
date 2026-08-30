"""Forward-edit detection, offline.

Every case here is one where counting wrongly would put ordinary record-keeping
into a finding about sponsors moving deadlines. That is the specific harm this
study could do, so the exclusions are tested harder than the inclusions.
"""

from __future__ import annotations

import datetime as dt

from embargo.drift import DriftEvent, VersionStatus, detect, is_drift, project

D = dt.date


def v(
    version: int,
    version_date: str,
    completion: str | None,
    ctype: str | None = "ESTIMATED",
    start: str | None = "2015-01-01",
) -> VersionStatus:
    return VersionStatus(
        nct_id="NCT1",
        version=version,
        version_date=D.fromisoformat(version_date),
        primary_completion=D.fromisoformat(completion) if completion else None,
        completion_type=ctype,
        start_date=D.fromisoformat(start) if start else None,
        overall_status="RECRUITING",
    )


class TestIsDrift:
    def test_a_forward_edit_counts(self):
        assert is_drift(v(1, "2016-01-01", "2016-06-01"), v(2, "2016-02-01", "2017-06-01"))

    def test_a_backward_edit_does_not(self):
        """Moving the date earlier shortens the deadline. Counting it would make
        the number mean something other than its name."""
        assert not is_drift(v(1, "2016-01-01", "2017-06-01"), v(2, "2016-02-01", "2016-06-01"))

    def test_an_unchanged_date_does_not(self):
        assert not is_drift(v(1, "2016-01-01", "2016-06-01"), v(2, "2016-02-01", "2016-06-01"))

    def test_estimate_becoming_actual_does_not(self):
        """The most important exclusion.

        A trial that finished later than planned records that fact, and the date
        moves forward. That is the registry working, not a deadline being moved,
        and counting it would fill the result with routine record-keeping.
        """
        before = v(1, "2016-01-01", "2016-06-01", ctype="ESTIMATED")
        after = v(2, "2016-08-01", "2016-07-15", ctype="ACTUAL")
        assert not is_drift(before, after)

    def test_estimate_to_later_estimate_does_count(self):
        before = v(1, "2016-01-01", "2016-06-01", ctype="ESTIMATED")
        after = v(2, "2016-02-01", "2017-06-01", ctype="ESTIMATED")
        assert is_drift(before, after)

    def test_actual_to_later_actual_does_count(self):
        """A date already recorded as actual, moved later, is not an estimate
        resolving. Something was restated."""
        before = v(1, "2016-01-01", "2016-06-01", ctype="ACTUAL")
        after = v(2, "2017-02-01", "2016-09-01", ctype="ACTUAL")
        assert is_drift(before, after)

    def test_an_edit_before_the_study_started_does_not_count(self):
        """Planning, not a deadline moving."""
        before = v(1, "2014-01-01", "2016-06-01", start="2015-01-01")
        after = v(2, "2014-06-01", "2017-06-01", start="2015-01-01")
        assert not is_drift(before, after)

    def test_a_missing_date_on_either_side_does_not_count(self):
        assert not is_drift(v(1, "2016-01-01", None), v(2, "2016-02-01", "2017-01-01"))
        assert not is_drift(v(1, "2016-01-01", "2016-06-01"), v(2, "2016-02-01", None))

    def test_a_missing_start_date_does_not_block_detection(self):
        """Absent is not disqualifying. Treating a missing start date as
        'before the study started' would silently drop every record that omits
        one."""
        before = v(1, "2016-01-01", "2016-06-01", start=None)
        after = v(2, "2016-02-01", "2017-06-01", start=None)
        assert is_drift(before, after)


class TestDetect:
    def test_finds_each_forward_edit_in_a_trajectory(self):
        events = detect(
            [
                v(0, "2015-02-01", "2016-06-01"),
                v(1, "2016-01-01", "2017-06-01"),
                v(2, "2017-01-01", "2018-06-01"),
            ]
        )
        assert [e.to_version for e in events] == [1, 2]
        assert [e.moved_days for e in events] == [365, 365]

    def test_skips_revisions_that_state_no_date(self):
        """A revision that dropped the field and one that restored it must not
        read as two edits with a gap between them."""
        events = detect(
            [
                v(0, "2015-02-01", "2016-06-01"),
                v(1, "2015-03-01", None),
                v(2, "2015-04-01", "2017-06-01"),
            ]
        )
        assert len(events) == 1
        assert events[0].from_version == 0 and events[0].to_version == 2

    def test_orders_by_version_not_by_input_order(self):
        events = detect([v(2, "2017-01-01", "2018-06-01"), v(1, "2016-01-01", "2017-06-01")])
        assert events and events[0].from_version == 1

    def test_a_record_that_never_moved_produces_nothing(self):
        assert detect([v(0, "2015-02-01", "2016-06-01"), v(1, "2016-01-01", "2016-06-01")]) == []

    def test_an_empty_trajectory_is_not_an_error(self):
        assert detect([]) == []

    def test_moved_days_is_the_size_of_the_deadline_shift(self):
        e = detect([v(0, "2015-02-01", "2016-06-01"), v(1, "2016-01-01", "2016-07-01")])[0]
        assert isinstance(e, DriftEvent)
        assert e.moved_days == 30


class TestProject:
    def test_pulls_the_dates_from_a_history_payload(self):
        payload = {
            "study": {
                "protocolSection": {
                    "statusModule": {
                        "overallStatus": "COMPLETED",
                        "startDateStruct": {"date": "2015-01-01"},
                        "primaryCompletionDateStruct": {
                            "date": "2016-06-01",
                            "type": "ESTIMATED",
                        },
                    }
                }
            }
        }
        vs = project("NCT1", 3, D(2016, 1, 1), payload)
        assert vs.primary_completion == D(2016, 6, 1)
        assert vs.completion_type == "ESTIMATED"
        assert vs.start_date == D(2015, 1, 1)
        assert vs.overall_status == "COMPLETED"

    def test_a_record_without_dates_projects_to_nulls(self):
        vs = project("NCT1", 0, D(2015, 1, 1), {"study": {"protocolSection": {}}})
        assert vs.primary_completion is None
        assert vs.start_date is None

    def test_month_precision_resolves_to_the_first(self):
        payload = {
            "protocolSection": {
                "statusModule": {"primaryCompletionDateStruct": {"date": "2016-06"}}
            }
        }
        assert project("NCT1", 0, D(2016, 1, 1), payload).primary_completion == D(2016, 6, 1)
