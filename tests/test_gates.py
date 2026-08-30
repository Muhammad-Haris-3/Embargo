"""The gates, made to fail.

A gate that has only ever passed is a gate nobody has shown can fail. These
drive Gate 2 with a fake registry and a fake warehouse so that both verdicts
are exercised, offline, on every commit.
"""

from __future__ import annotations

import pytest

from embargo import gates
from embargo.gates import GateResult, gate2_census_agrees


class FakeSource:
    """A registry with fixed opinions about how many trials posted each year."""

    def __init__(self, counts: dict[int, int]):
        self.counts = counts
        self.asked: list[int] = []

    def count(self, *, query_term: str, **_: str) -> int:
        year = int(query_term.split("RANGE[")[1][:4])
        self.asked.append(year)
        return self.counts.get(year, 0)


@pytest.fixture()
def census(monkeypatch):
    """Replace the warehouse query; the SQL is exercised against a real
    database by the gate itself, and what is tested here is the comparison."""

    def install(ours):
        monkeypatch.setattr(gates, "our_census", lambda conn, start, end: ours)

    return install


class TestGate2:
    def test_passes_when_every_year_agrees(self, census):
        census({2008: 41, 2009: 1099})
        result = gate2_census_agrees(None, FakeSource({2008: 41, 2009: 1099}), start=2008, end=2009)
        assert result.passed
        assert result.n_checked == 2
        assert result.n_failed == 0

    def test_fails_on_a_single_missing_trial(self, census):
        """No tolerance, and this is why it is written down as no tolerance.

        One trial short means one trial we do not hold. There is no threshold
        that makes that acceptable, and a gate with a threshold would be a gate
        that quietly tolerates a collection bug.
        """
        census({2008: 41, 2009: 1098})
        result = gate2_census_agrees(None, FakeSource({2008: 41, 2009: 1099}), start=2008, end=2009)
        assert not result.passed
        assert result.n_failed == 1
        assert result.worst_diff == 1
        assert result.detail["failures"] == [
            {"year": 2009, "ours": 1098, "registry": 1099, "diff": -1}
        ]

    def test_fails_when_we_hold_more_than_the_registry(self, census):
        """Over-counting is a failure too.

        A duplicate trial counted twice would inflate a year, and a gate that
        only checked for shortfalls would pass while the warehouse invented
        evidence.
        """
        census({2008: 42})
        result = gate2_census_agrees(None, FakeSource({2008: 41}), start=2008, end=2008)
        assert not result.passed
        assert result.detail["failures"][0]["diff"] == 1

    def test_a_year_we_hold_nothing_for_is_a_failure_not_a_skip(self, census):
        census({2008: 41, 2009: 0})
        result = gate2_census_agrees(None, FakeSource({2008: 41, 2009: 500}), start=2008, end=2009)
        assert not result.passed
        assert result.detail["failures"][0]["ours"] == 0

    def test_every_year_in_the_range_is_asked_about(self, census):
        census({y: 1 for y in range(2008, 2026)})
        source = FakeSource({y: 1 for y in range(2008, 2026)})
        result = gate2_census_agrees(None, source, start=2008, end=2025)
        assert source.asked == list(range(2008, 2026))
        assert result.n_checked == 18

    def test_the_current_year_is_not_in_the_census(self, census):
        """The current year is still accumulating postings, so comparing a live
        count against a snapshot would fail for a reason unrelated to capture.
        The preregistration stops the census at 2025 for exactly this."""
        from embargo.preregistration import CENSUS_END_YEAR

        assert CENSUS_END_YEAR < 2026


class TestGateResult:
    def test_str_shows_the_verdict(self):
        assert str(GateResult("g", True, 10, 0)).startswith("[PASS]")
        assert str(GateResult("g", False, 10, 3)).startswith("[FAIL]")

    def test_a_failed_gate_reports_its_failures(self):
        assert "3/10" in str(GateResult("g", False, 10, 3))
