"""Whether the primary outcome may be served.

`PREREGISTRATION.md` says the primary outcome is not computed, and no queue
estimate is published, until all three gates pass. Gate 3 currently fails.

That instruction could have been honoured by remembering not to add the
endpoint. It is honoured here instead, as a function the endpoint calls on
every request, because a rule that depends on nobody forgetting is not a rule.

The check is deliberately conservative in both directions a mistake could go:
a gate that has never run counts as not passed, and a gate whose most recent
result is a failure counts as not passed even if an earlier run passed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Named here rather than counted from whatever the database happens to hold. If
# gate_results is empty, the answer must be "three gates are required and none
# has run", not "all zero gates pass".
REQUIRED_GATES = ("capture_faithful", "census_agrees", "estimator_recovers")


@dataclass(frozen=True)
class Gating:
    publishable: bool
    passing: tuple[str, ...]
    failing: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def reason(self) -> str | None:
        if self.publishable:
            return None
        parts = []
        if self.failing:
            parts.append(f"{', '.join(self.failing)} failing")
        if self.missing:
            parts.append(f"{', '.join(self.missing)} never run")
        return (
            "The primary outcome is withheld because "
            + " and ".join(parts)
            + ". PREREGISTRATION.md requires all three gates to pass before any "
            "queue estimate is published."
        )


def evaluate_gates(latest: Iterable[tuple[str, bool]]) -> Gating:
    """Decide from the latest result per gate.

    `latest` is (gate name, passed) for the most recent run of each gate.
    """
    seen = dict(latest)
    passing = tuple(g for g in REQUIRED_GATES if seen.get(g) is True)
    failing = tuple(g for g in REQUIRED_GATES if seen.get(g) is False)
    missing = tuple(g for g in REQUIRED_GATES if g not in seen)
    return Gating(
        publishable=len(passing) == len(REQUIRED_GATES),
        passing=passing,
        failing=failing,
        missing=missing,
    )


def gates_from_rows(rows: Iterable[tuple[str, bool, Any]]) -> Gating:
    """Latest-per-gate from rows ordered newest first."""
    seen: dict[str, bool] = {}
    for gate, passed, _ in rows:
        seen.setdefault(gate, passed)
    return evaluate_gates(seen.items())
