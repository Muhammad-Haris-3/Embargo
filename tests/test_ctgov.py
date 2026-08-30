"""Parsing, offline, on fixtures shaped like real records.

These run on a fresh clone with no network and no database. The shapes here are
taken from real responses observed on 2026-08-30; where a field is unusual, the
docstring says which record it came from.
"""

from __future__ import annotations

import datetime as dt

from embargo.ctgov import Version, parse_date, status_dates, wait_days

# NCT04368728 as it stands today, trimmed to the fields the collector reads.
# Submitted 2024-02-09, posted 2026-03-25: a wait of 775 days.
POSTED = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT04368728", "briefTitle": "A study"},
        "statusModule": {
            "overallStatus": "COMPLETED",
            "primaryCompletionDateStruct": {"date": "2023-02-10", "type": "ACTUAL"},
            "resultsFirstSubmitDate": "2024-02-09",
            "resultsFirstSubmitQcDate": "2026-03-03",
            "resultsFirstPostDateStruct": {"date": "2026-03-25", "type": "ACTUAL"},
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "BioNTech SE", "class": "INDUSTRY"}},
    },
    "hasResults": True,
}

# The shape of every record that matters and cannot be found: completed, no
# results anywhere in the public payload.
UNPOSTED = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT06203331", "briefTitle": "Another study"},
        "statusModule": {
            "overallStatus": "COMPLETED",
            "primaryCompletionDateStruct": {"date": "2024-08-01", "type": "ACTUAL"},
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "A University", "class": "OTHER"}},
    },
    "hasResults": False,
}


class TestParseDate:
    def test_full_date(self):
        assert parse_date("2024-02-09") == (dt.date(2024, 2, 9), False)

    def test_month_precision_resolves_to_the_first(self):
        """PREREGISTRATION.md fixes this convention and requires the flag."""
        assert parse_date("2026-03") == (dt.date(2026, 3, 1), True)

    def test_year_precision(self):
        assert parse_date("2019") == (dt.date(2019, 1, 1), True)

    def test_missing(self):
        assert parse_date(None) == (None, False)
        assert parse_date("") == (None, False)

    def test_nonsense_does_not_raise(self):
        assert parse_date("not-a-date") == (None, False)

    def test_basic_format_is_not_a_date(self):
        """20260830 is a seed, not August 2026.

        date.fromisoformat accepts the basic format, which is exactly how a
        constant becomes a date without anyone noticing.
        """
        assert parse_date("20260830")[0] != dt.date(2026, 8, 30)


class TestStatusDates:
    def test_posted_record(self):
        d = status_dates(POSTED)
        assert d["nct_id"] == "NCT04368728"
        assert d["results_first_submit"] == dt.date(2024, 2, 9)
        assert d["results_first_post"] == dt.date(2026, 3, 25)
        assert d["sponsor_class"] == "INDUSTRY"
        assert d["has_partial_date"] is False

    def test_unposted_record_has_neither_date(self):
        d = status_dates(UNPOSTED)
        assert d["results_first_submit"] is None
        assert d["results_first_post"] is None
        assert d["has_results"] is False

    def test_empty_record_does_not_raise(self):
        assert status_dates({})["nct_id"] is None


class TestWaitDays:
    def test_the_quantity_the_project_is_about(self):
        assert wait_days(status_dates(POSTED)) == 775

    def test_unposted_has_no_wait(self):
        assert wait_days(status_dates(UNPOSTED)) is None

    def test_negative_wait_is_returned_not_clamped(self):
        """A clamp moves the median in a known direction.

        PREREGISTRATION.md requires negative waits to be excluded and counted by
        the caller. Silently returning zero here would make that impossible.
        """
        broken = {
            "protocolSection": {
                "identificationModule": {"nctId": "NCT00000000"},
                "statusModule": {
                    "resultsFirstSubmitDate": "2024-06-01",
                    "resultsFirstPostDateStruct": {"date": "2024-05-01"},
                },
            }
        }
        assert wait_days(status_dates(broken)) == -31


class TestVersion:
    def make(self, labels):
        return Version(
            nct_id="NCT1",
            version=1,
            version_date=dt.date(2024, 1, 1),
            status="COMPLETED",
            module_labels=tuple(labels),
        )

    def test_results_module_is_recognised(self):
        assert self.make(["Study Status", "Outcome Measures (Results)"]).touched_results

    def test_adverse_events_results_counts(self):
        assert self.make(["Adverse Events (Results)"]).touched_results

    def test_protocol_only_revision_does_not(self):
        """The distinction the history sweep depends on.

        'Outcome Measures' without '(Results)' is a protocol edit -- the sponsor
        changing what it says it will measure. That is the deadline-drift study,
        not the queue study, and conflating them would put protocol churn into
        the wait.
        """
        assert not self.make(["Study Status", "Contacts/Locations"]).touched_results
        assert not self.make(["Outcome Measure"]).touched_results
