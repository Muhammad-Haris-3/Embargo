"""The preregistered gates.

`PREREGISTRATION.md` fixes three, and requires all of them to pass before the
primary outcome is computed at all. They are not robustness checks run
afterwards on a result somebody already likes.

Gate 1 is implemented here. Gates 2 and 3 arrive at M3 and M4, and this module
records every result to `gate_results` so that a verdict is a row in a database
rather than a sentence in a document.

A gate that fails is published. `scripts` and CI return the verdict as an exit
status, so a failed gate fails the build and keeps failing until the problem is
resolved rather than tuned away.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any

from .ctgov import CtGov
from .pit import status_module_of, store_version
from .preregistration import GATE1_SAMPLE_SIZE, GATE1_SEED


@dataclass
class GateResult:
    gate: str
    passed: bool
    n_checked: int
    n_failed: int
    worst_diff: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def record(self, conn: Any) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gate_results
                    (gate, passed, n_checked, n_failed, worst_diff, detail)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    self.gate,
                    self.passed,
                    self.n_checked,
                    self.n_failed,
                    self.worst_diff,
                    json.dumps(self.detail, default=str),
                ),
            )

    def __str__(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return f"[{verdict}] {self.gate}  {self.n_failed}/{self.n_checked} failed"


def sample_versions(conn: Any, size: int, seed: int) -> list[tuple[str, int]]:
    """Draw (nct_id, version) pairs under the preregistered seed.

    The seed is fixed in `PREREGISTRATION.md` so the sample cannot be redrawn
    until it passes. Ordering is made deterministic in SQL before sampling,
    because a seeded draw over a non-deterministic row order is not reproducible
    and would quietly become a fresh sample on every run.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT nct_id, version FROM record_versions ORDER BY nct_id, version")
        population = cur.fetchall()

    if not population:
        return []
    rng = random.Random(seed)
    size = min(size, len(population))
    return [tuple(pair) for pair in rng.sample(population, size)]


def gate1_capture_is_faithful(
    conn: Any,
    source: CtGov,
    run_id: int,
    *,
    size: int = GATE1_SAMPLE_SIZE,
    seed: int = GATE1_SEED,
) -> GateResult:
    """Gate 1 -- what we stored is what the source served.

    For each sampled revision: store it if we do not hold it, then read our
    stored copy back out of the database and compare its status module, field
    for field, against a fresh fetch from the API.

    This tests storage and joins, not arithmetic. The round trip through jsonb
    is where a date becomes a string, a null becomes absent, or a key order
    changes -- none of which is visible until something downstream computes a
    wrong number from it.
    """
    pairs = sample_versions(conn, size, seed)
    failures: list[dict[str, Any]] = []

    for nct_id, version in pairs:
        try:
            store_version(conn, run_id, source, nct_id, version)
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            failures.append({"nct_id": nct_id, "version": version, "error": repr(exc)})
            continue

        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM version_payloads WHERE nct_id = %s AND version = %s",
                (nct_id, version),
            )
            row = cur.fetchone()
        if row is None:
            failures.append({"nct_id": nct_id, "version": version, "error": "not stored"})
            continue

        ours = status_module_of(row[0])
        theirs = status_module_of(source.version(nct_id, version))
        if ours != theirs:
            differing = sorted(k for k in set(ours) | set(theirs) if ours.get(k) != theirs.get(k))
            failures.append(
                {
                    "nct_id": nct_id,
                    "version": version,
                    "differing_fields": differing,
                    "ours": {k: ours.get(k) for k in differing},
                    "theirs": {k: theirs.get(k) for k in differing},
                }
            )

    return GateResult(
        gate="capture_faithful",
        # Preregistered at zero tolerance: this is an identity check, and a
        # single disagreement means the store is not holding what it was given.
        passed=len(pairs) > 0 and not failures,
        n_checked=len(pairs),
        n_failed=len(failures),
        worst_diff=None,
        detail={
            "seed": seed,
            "requested_size": size,
            "failures": failures[:20],
            "empty_population": not pairs,
        },
    )
