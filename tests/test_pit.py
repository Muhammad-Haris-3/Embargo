"""Point-in-time reconstruction, against a fake store.

These run offline. The SQL is exercised by the gate itself against a real
database; what is tested here is the rule that decides which revision was
current, because that rule is one comparison and getting it wrong by a day
would be invisible in every output.
"""

from __future__ import annotations

import datetime as dt

from embargo.knowability import AsOf
from embargo.pit import status_module_of, version_current_on

# A record touched three times. Between revisions it did not change, because
# nobody changed it -- there is no intermediate state to invent.
VERSIONS = [
    (0, dt.date(2015, 3, 1)),
    (1, dt.date(2016, 9, 14)),
    (2, dt.date(2020, 1, 20)),
]


class FakeCursor:
    def __init__(self, versions):
        self.versions = versions
        self._row = None

    def execute(self, sql, params):
        _, cutoff = params
        eligible = [(v, d) for v, d in self.versions if d <= cutoff]
        self._row = (max(eligible, key=lambda p: (p[1], p[0]))[0],) if eligible else None

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, versions=VERSIONS):
        self.versions = versions

    def cursor(self):
        return FakeCursor(self.versions)


class TestVersionCurrentOn:
    def test_between_revisions_the_earlier_one_stands(self):
        """On 2016-01-01 the record looked exactly as it did in March 2015."""
        assert version_current_on(FakeConn(), "NCT1", AsOf(dt.date(2016, 1, 1))) == 0

    def test_on_the_day_of_a_revision_that_revision_is_current(self):
        assert version_current_on(FakeConn(), "NCT1", AsOf(dt.date(2016, 9, 14))) == 1

    def test_the_day_before_a_revision_it_is_not(self):
        assert version_current_on(FakeConn(), "NCT1", AsOf(dt.date(2016, 9, 13))) == 0

    def test_after_the_last_revision_the_last_one_stands(self):
        assert version_current_on(FakeConn(), "NCT1", AsOf(dt.date(2026, 1, 1))) == 2

    def test_before_the_record_existed_there_is_no_version(self):
        """Not an error. A fact about the date."""
        assert version_current_on(FakeConn(), "NCT1", AsOf(dt.date(2014, 1, 1))) is None

    def test_a_future_revision_is_never_chosen(self):
        """The reconstruction must not reach forward, which is the failure that
        produces a plausible number rather than an obvious one."""
        for as_of, expected in [
            (dt.date(2015, 3, 1), 0),
            (dt.date(2019, 12, 31), 1),
            (dt.date(2020, 1, 20), 2),
        ]:
            assert version_current_on(FakeConn(), "NCT1", AsOf(as_of)) == expected


class TestStatusModuleOf:
    def test_unwraps_the_history_route_shape(self):
        """A version from /api/int arrives wrapped in `study`."""
        payload = {"study": {"protocolSection": {"statusModule": {"overallStatus": "COMPLETED"}}}}
        assert status_module_of(payload) == {"overallStatus": "COMPLETED"}

    def test_handles_the_documented_api_shape(self):
        payload = {"protocolSection": {"statusModule": {"overallStatus": "RECRUITING"}}}
        assert status_module_of(payload) == {"overallStatus": "RECRUITING"}

    def test_missing_module_is_empty_not_an_error(self):
        assert status_module_of({}) == {}
        assert status_module_of({"study": {}}) == {}
