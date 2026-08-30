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
from .preregistration import (
    CENSUS_END_YEAR,
    CENSUS_START_YEAR,
    GATE1_SAMPLE_SIZE,
    GATE1_SEED,
    QUEUE_TOL,
)


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


# The path through a landing payload to the day results became readable. Written
# once: it appears in SQL and in Python, and the two drifting apart would make
# the gate compare our count against a different question.
POST_DATE_PATH = "payload->'protocolSection'->'statusModule'->'resultsFirstPostDateStruct'->>'date'"


def our_census(conn: Any, start: int, end: int) -> dict[int, int]:
    """Trials whose results were first posted in each year, per our warehouse.

    Counted over the latest payload per trial. A trial that was captured twice
    is one trial, and counting landing rows instead of trials would inflate
    every year in which anything was recaptured.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (nct_id) nct_id, payload
                  FROM landing_study
                 ORDER BY nct_id, captured_at DESC
            )
            SELECT left({POST_DATE_PATH}, 4)::int AS yr, count(*)
              FROM latest
             WHERE {POST_DATE_PATH} IS NOT NULL
             GROUP BY yr
            """
        )
        counts = dict(cur.fetchall())
    return {year: counts.get(year, 0) for year in range(start, end + 1)}


def gate2_census_agrees(
    conn: Any,
    source: CtGov,
    *,
    start: int = CENSUS_START_YEAR,
    end: int = CENSUS_END_YEAR,
) -> GateResult:
    """Gate 2 -- our per-year counts equal the registry's own.

    Exactly. A count is not a measurement and has no tolerance: if the registry
    says 4,312 trials posted results in 2019 and we hold 4,311, we are missing
    one, and no threshold makes that acceptable.

    The census stops at CENSUS_END_YEAR deliberately. The current year is still
    accumulating postings, so comparing a live count against a snapshot taken
    this morning would fail for a reason that has nothing to do with capture.
    """
    ours = our_census(conn, start, end)
    failures = []
    worst = 0

    for year in range(start, end + 1):
        theirs = source.count(
            query_term=f"AREA[ResultsFirstPostDate]RANGE[{year}-01-01,{year}-12-31]"
        )
        mine = ours.get(year, 0)
        if mine != theirs:
            diff = mine - theirs
            worst = max(worst, abs(diff))
            failures.append({"year": year, "ours": mine, "registry": theirs, "diff": diff})

    return GateResult(
        gate="census_agrees",
        passed=not failures,
        n_checked=end - start + 1,
        n_failed=len(failures),
        worst_diff=worst or None,
        detail={
            "years": f"{start}-{end}",
            "ours": ours,
            "failures": failures,
        },
    )


def gate3_estimator_recovers(
    conn: Any,
    records: list[dict[str, Any]],
    run_id: int,
    *,
    tol: float = QUEUE_TOL,
) -> GateResult:
    """Gate 3 -- the estimator recovers a queue whose size is already known.

    The gate the project exists to pass, and the first that can fail on its
    merits rather than on plumbing.

    Two conditions, both preregistered:

    1. At every **mature** grid date, `Qhat` must be within `QUEUE_TOL` of
       `Qstar`.
    2. At **any** grid date, mature or not, `Qhat` below `Qstar` is a failure.
       `Qstar` is a lower bound built from disclosures that have already
       happened; an estimate beneath it has contradicted something on the table.

    Every point is committed to the register before it is judged, including the
    ones that fail. A register holding only the estimates that turned out well
    would answer a different question than the one asked.
    """
    from .queue import commit, evaluate, freeze_grid

    failures: list[dict[str, Any]] = []
    checked = 0
    mature_checked = 0
    worst = 0.0
    points = []

    for freeze_date in freeze_grid():
        point = evaluate(records, freeze_date)
        commit(conn, run_id, point)
        conn.commit()
        points.append(point)

        error = point.relative_error
        summary = {
            "freeze_date": freeze_date.isoformat(),
            "q_hat": round(point.estimate.q_hat, 1),
            "q_star_lower": point.q_star,
            "relative_error": round(error, 4) if error is not None else None,
            "mature": point.mature,
        }

        # Every grid date is examined, whichever way it fails. Counting only
        # the ones that reached the tolerance test produced "6/0 failed", which
        # is not a possible thing for a gate to report.
        checked += 1

        # Worst error over every point examined. Accumulating it only where the
        # tolerance test was reached reported worst_diff as null on a gate that
        # missed by 90%.
        if error is not None:
            worst = max(worst, abs(error))

        if point.below_the_bound:
            failures.append({**summary, "reason": "below the realised lower bound"})
            continue

        if point.mature:
            mature_checked += 1
            if error is not None and abs(error) > tol:
                failures.append({**summary, "reason": f"outside tolerance {tol}"})

    return GateResult(
        gate="estimator_recovers",
        passed=mature_checked > 0 and not failures,
        n_checked=checked,
        n_failed=len(failures),
        worst_diff=round(worst, 4) or None,
        detail={
            "tolerance": tol,
            "mature_dates_checked": mature_checked,
            "grid": [p.freeze_date.isoformat() for p in points],
            "mature_dates": [p.freeze_date.isoformat() for p in points if p.mature],
            "points": [
                {
                    "freeze_date": p.freeze_date.isoformat(),
                    "q_hat": round(p.estimate.q_hat, 1),
                    "q_star_lower": p.q_star,
                    "relative_error": round(p.relative_error, 4)
                    if p.relative_error is not None
                    else None,
                    "mature": p.mature,
                    "excluded_share": round(p.estimate.excluded_share, 4),
                }
                for p in points
            ],
            "failures": failures,
            "no_mature_dates": mature_checked == 0,
        },
    )
