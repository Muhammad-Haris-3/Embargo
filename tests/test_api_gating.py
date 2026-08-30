"""The refusal, tested without a database.

`PREREGISTRATION.md` says no queue estimate is published until all three gates
pass. That could have been honoured by not writing the endpoint. It is honoured
by a function the endpoint calls on every request instead, because a rule that
depends on nobody forgetting is not a rule -- and this is the file that would
fail if someone later made it forget.
"""

from __future__ import annotations

import pytest

from api.gating import REQUIRED_GATES, evaluate_gates, gates_from_rows

ALL_PASS = [(g, True) for g in REQUIRED_GATES]


class TestEvaluateGates:
    def test_publishable_only_when_all_three_pass(self):
        assert evaluate_gates(ALL_PASS).publishable

    def test_one_failing_gate_withholds_everything(self):
        latest = [
            ("capture_faithful", True),
            ("census_agrees", True),
            ("estimator_recovers", False),
        ]
        gating = evaluate_gates(latest)
        assert not gating.publishable
        assert gating.failing == ("estimator_recovers",)

    def test_a_gate_that_never_ran_counts_as_not_passed(self):
        """The dangerous default.

        Counting only the gates present would make an empty table read as "all
        zero gates pass", which is how a preregistration gets satisfied by
        having run nothing.
        """
        gating = evaluate_gates([("capture_faithful", True)])
        assert not gating.publishable
        assert set(gating.missing) == {"census_agrees", "estimator_recovers"}

    def test_no_gates_at_all_is_not_permission(self):
        gating = evaluate_gates([])
        assert not gating.publishable
        assert len(gating.missing) == len(REQUIRED_GATES)

    def test_an_unknown_gate_does_not_count_towards_the_three(self):
        """A renamed or invented gate must not be able to satisfy the rule."""
        gating = evaluate_gates([*ALL_PASS[:2], ("something_else", True)])
        assert not gating.publishable
        assert "estimator_recovers" in gating.missing

    def test_the_reason_names_the_failing_gate(self):
        gating = evaluate_gates(
            [("capture_faithful", True), ("census_agrees", True), ("estimator_recovers", False)]
        )
        assert "estimator_recovers" in gating.reason
        assert "PREREGISTRATION" in gating.reason

    def test_a_publishable_state_has_no_reason_to_withhold(self):
        assert evaluate_gates(ALL_PASS).reason is None


class TestGatesFromRows:
    def test_takes_the_most_recent_result_per_gate(self):
        """Rows arrive newest first, and the newest verdict is the verdict."""
        rows = [
            ("estimator_recovers", False, "2026-08-30"),
            ("estimator_recovers", True, "2026-08-01"),
            ("capture_faithful", True, "2026-08-30"),
            ("census_agrees", True, "2026-08-30"),
        ]
        gating = gates_from_rows(rows)
        assert not gating.publishable
        assert gating.failing == ("estimator_recovers",)

    def test_an_earlier_pass_does_not_rescue_a_later_failure(self):
        """The failure mode this exists to prevent: a gate that passed once,
        then broke, and whose old verdict is still on the record."""
        rows = [("estimator_recovers", False, "b"), ("estimator_recovers", True, "a")]
        assert not gates_from_rows(rows).publishable


class TestCurrentState:
    def test_the_project_is_currently_withholding(self):
        """Documents the live state, and will fail when Gate 3 starts passing --
        at which point the M4 summary and the README both need rewriting, and a
        failing test is a better reminder than a resolution to remember."""
        gating = evaluate_gates(
            [("capture_faithful", True), ("census_agrees", True), ("estimator_recovers", False)]
        )
        assert not gating.publishable


@pytest.mark.parametrize("gate", REQUIRED_GATES)
def test_every_required_gate_can_individually_block(gate):
    latest = [(g, g != gate) for g in REQUIRED_GATES]
    assert not evaluate_gates(latest).publishable
