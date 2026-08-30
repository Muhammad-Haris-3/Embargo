"""Run the deadline-drift study.

Collects the status projection for a seeded sample of trials, detects forward
edits, and writes both the events and the summary.

**It computes the finding and then declines to print it.**
`PREREGISTRATION.md` scopes the secondary study as "reported only if the primary
gates pass", and Gate 3 fails. The numbers are stored either way, because a
study that only records itself when the answer is allowed out is not a record.

Usage:
    python -m embargo.run_drift --collect-minutes 25
    python -m embargo.run_drift --summarise-only
"""

from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys
import time
from typing import Any

from .config import settings
from .ctgov import CtGov
from .db import connect
from .drift import (
    collect_trial,
    detect,
    sample_trials,
    sponsor_classes,
    stored_trajectory,
)
from .http import Http
from .preregistration import DRIFT_SAMPLE_SIZE, DRIFT_SEED
from .runlog import run as run_log

REQUIRED_GATES = ("capture_faithful", "census_agrees", "estimator_recovers")


def primary_gates_pass(conn: Any) -> tuple[bool, list[str]]:
    """The condition the whole study is scoped behind.

    A gate that has never run counts as not passed, for the same reason it does
    in the API: an empty table must not read as "all zero gates pass".
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (gate) gate, passed
              FROM gate_results
             ORDER BY gate, checked_at DESC
            """
        )
        latest = dict(cur.fetchall())
    blocking = [g for g in REQUIRED_GATES if latest.get(g) is not True]
    return not blocking, blocking


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deadline-drift study")
    parser.add_argument("--collect-minutes", type=float, default=25.0)
    parser.add_argument("--summarise-only", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    cfg = settings()
    with Http(
        user_agent=cfg.user_agent,
        min_interval_s=cfg.min_interval_s,
        max_retries=cfg.max_retries,
    ) as http:
        source = CtGov(http)
        with connect() as conn, run_log(conn, "drift", source=source) as state:
            trials = sample_trials(conn)
            if not trials:
                print("no collected history to sample from", file=sys.stderr)
                return 1

            collected = 0
            if not args.summarise_only:
                deadline = time.monotonic() + args.collect_minutes * 60
                for nct_id in trials:
                    if time.monotonic() >= deadline:
                        break
                    try:
                        collected += collect_trial(conn, state.run_id, source, nct_id)
                        conn.commit()
                    except Exception as exc:  # noqa: BLE001
                        state.detail.setdefault("errors", []).append(f"{nct_id}: {exc!r}")

            classes = sponsor_classes(conn, trials)
            stamp = dt.datetime.now(dt.UTC)
            reportable, blocking = primary_gates_pass(conn)

            per_class: dict[str, dict[str, Any]] = {}
            complete = 0
            for nct_id in trials:
                trajectory = stored_trajectory(conn, nct_id)
                if not trajectory:
                    continue
                complete += 1
                events = detect(trajectory)
                cls = classes.get(nct_id, "UNKNOWN")
                bucket = per_class.setdefault(
                    cls, {"trials": 0, "with_drift": 0, "edits": 0, "moved": []}
                )
                bucket["trials"] += 1
                if events:
                    bucket["with_drift"] += 1
                    bucket["edits"] += len(events)
                    bucket["moved"].extend(e.moved_days for e in events)
                for e in events:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO drift_events
                                (computed_at, nct_id, from_version, to_version,
                                 edited_on, from_date, to_date, moved_days,
                                 from_type, to_type, sponsor_class)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                stamp,
                                e.nct_id,
                                e.from_version,
                                e.to_version,
                                e.edited_on,
                                e.from_date,
                                e.to_date,
                                e.moved_days,
                                e.from_type,
                                e.to_type,
                                cls,
                            ),
                        )

            for cls, b in sorted(per_class.items()):
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO drift_summary
                            (computed_at, sponsor_class, trials_sampled,
                             trials_with_drift, edits, median_moved_days,
                             max_moved_days, sample_size, sample_seed, reportable)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            stamp,
                            cls,
                            b["trials"],
                            b["with_drift"],
                            b["edits"],
                            int(statistics.median(b["moved"])) if b["moved"] else None,
                            max(b["moved"]) if b["moved"] else None,
                            DRIFT_SAMPLE_SIZE,
                            DRIFT_SEED,
                            reportable,
                        ),
                    )
            conn.commit()

            state.rows_appended = collected
            state.http_calls = http.calls
            state.note(
                sampled=len(trials),
                trajectories_available=complete,
                version_rows_added=collected,
                reportable=reportable,
                blocked_by=blocking,
            )

    print(f"sampled {len(trials)} trials; {complete} have a stored trajectory")
    print(f"collected {collected} version-status rows this run")
    print()

    if reportable:
        for cls, b in sorted(per_class.items()):
            print(f"  {cls:<12} {b['with_drift']}/{b['trials']} trials, {b['edits']} edits")
        return 0

    # The finding exists, is stored, and is not printed.
    print("FINDING WITHHELD")
    print(f"  blocked by: {', '.join(blocking)}")
    print(
        "  PREREGISTRATION.md scopes the secondary study as reported only if\n"
        "  the primary gates pass. The events and summary are in the database,\n"
        "  flagged reportable=false, and are not shown here."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
