"""The M0 collector.

What it does, and why it is shaped this way.

The registry will not tell us which results are waiting. It will only tell us,
after the fact, that some particular result waited. So the collector watches the
one event that is observable -- a posting -- and, each time one happens, asks
that record for its full revision history. That history contains the versions
submitted during the wait, which is where the wait becomes measurable.

Two sweeps, both idempotent, both safe to run twice:

  postings   every record whose results were first posted since a cutoff, landed
             as raw payload, insert-if-changed
  history    for records we have landed but never historied, the revision list

The history sweep is the expensive one -- one call per record -- so it runs
under a budget and picks up where it left off. A run that exhausts its budget is
not a failure; it is a run that will finish tomorrow, and the run log says so.

Nothing here derives a wait, estimates a queue, or computes a finding. M0
collects, and PREREGISTRATION.md fixes what may be computed later and after
which gates.

Usage:
    python -m embargo.ingest --job daily
    python -m embargo.ingest --job backfill --since 2008-01-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from typing import Any

from .clock import today_utc
from .config import settings
from .ctgov import CtGov, status_dates
from .db import canonical_sha256, connect
from .http import Http
from .preregistration import CENSUS_START_YEAR
from .runlog import Run
from .runlog import run as run_log

# How far back a daily run looks. Generous on purpose: the sweep is
# insert-if-changed, so overlapping windows cost a little bandwidth and buy
# tolerance for a scheduler that missed a day.
DAILY_LOOKBACK_DAYS = 14

# History calls per run. One call per record, and there are tens of thousands of
# records, so the backlog is drained over days rather than in one burst against
# an undocumented endpoint.
DEFAULT_HISTORY_BUDGET = 400

# Rows per INSERT. Each statement is one round trip, and round trip is the
# entire cost of this job against a hosted database.
INSERT_BATCH = 500

# Wall-clock box for the history sweep, in minutes.
#
# The sweep used to be bounded by call count alone, and a budget of 3,000 ran
# 47.5 minutes into a 50 minute job and was killed with 100 calls left. A count
# is the wrong bound: what runs out is time, and per-call latency is not ours to
# predict. Measured against the live endpoint, a record history costs about
# 0.98s, of which only 0.35s is our own throttle.
#
# The count budget stays as a secondary cap, but this is what actually governs.
HISTORY_MINUTES = 25


def posted_since(since: dt.date) -> str:
    """Search term for records whose results were first posted on or after a date."""
    return f"AREA[ResultsFirstPostDate]RANGE[{since.isoformat()},MAX]"


def study_row(state: Run, study: dict[str, Any]) -> tuple | None:
    """Shape one study record for insertion, or None if it has no identifier."""
    nct_id = status_dates(study)["nct_id"]
    if not nct_id:
        return None
    return (
        nct_id,
        canonical_sha256(study),
        state.run_id,
        json.dumps(study, default=str),
    )


def land_studies(conn: Any, rows: list[tuple]) -> int:
    """Insert a batch of payloads, skipping content already seen.

    One statement per batch rather than one per row. The first backfill ran at
    15 rows/sec against Neon -- about 65ms each, essentially all of it round
    trip -- which put 80,000 records well past the job timeout. The work was
    never the database; it was asking it 80,000 separate times.

    ON CONFLICT DO NOTHING still reports the rows actually written, so
    insert-if-changed keeps its meaning: re-reading an unchanged record costs a
    little bandwidth and adds nothing.
    """
    if not rows:
        return 0
    placeholders = ",".join(["(%s, %s, %s, %s::jsonb)"] * len(rows))
    flat = [value for row in rows for value in row]
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO landing_study (nct_id, content_sha256, ingest_run_id, payload) "
            f"VALUES {placeholders} "
            "ON CONFLICT (nct_id, content_sha256) DO NOTHING",
            flat,
        )
        return cur.rowcount


def land_history(conn: Any, state: Run, source: CtGov, nct_id: str) -> int:
    """Fetch and store a record revision list. Returns rows appended."""
    versions = source.history(nct_id)
    if not versions:
        return 0

    rows = [
        (
            v.nct_id,
            v.version,
            v.version_date,
            v.status,
            list(v.module_labels),
            v.touched_results,
            state.run_id,
        )
        for v in versions
    ]
    placeholders = ",".join(["(%s, %s, %s, %s, %s, %s, %s)"] * len(rows))
    flat = [value for row in rows for value in row]
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO record_versions (nct_id, version, version_date, status, "
            "module_labels, touched_results, ingest_run_id) "
            f"VALUES {placeholders} "
            "ON CONFLICT (nct_id, version) DO NOTHING",
            flat,
        )
        return cur.rowcount


def needs_history(conn: Any, limit: int) -> list[str]:
    """Landed records we have never asked for a revision list.

    Ordered oldest-landed first, so the backlog drains in the order it arrived
    rather than re-treading whatever the last search happened to return.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT l.nct_id
              FROM landing_study l
             WHERE NOT EXISTS (
                   SELECT 1 FROM record_versions rv WHERE rv.nct_id = l.nct_id
             )
             GROUP BY l.nct_id
             ORDER BY min(l.captured_at)
             LIMIT %s
            """,
            (limit,),
        )
        return [row[0] for row in cur.fetchall()]


def sweep_postings(
    conn: Any, state: Run, source: CtGov, since: dt.date, *, max_pages: int | None = None
) -> int:
    appended = 0
    seen = 0
    batch: list[tuple] = []
    for study in source.search(query_term=posted_since(since), max_pages=max_pages):
        seen += 1
        row = study_row(state, study)
        if row is not None:
            batch.append(row)
        # Write and commit in batches. A long sweep that dies at page 40 should
        # keep the first 39 pages, because the alternative is a collector that
        # can only succeed completely and therefore, on a bad day, never.
        if len(batch) >= INSERT_BATCH:
            appended += land_studies(conn, batch)
            conn.commit()
            batch = []
    appended += land_studies(conn, batch)
    conn.commit()
    state.note(postings_seen=seen, postings_appended=appended, since=since.isoformat())
    return appended


def sweep_history(conn: Any, state: Run, source: CtGov, budget: int, minutes: float) -> int:
    """Fetch revision lists until the budget or the clock runs out.

    Stopping early is normal and is not a failure. The backlog is tens of
    thousands of records and is drained over days; what matters is that a run
    ends on its own terms, closes its row in the log, and leaves the rest for
    tomorrow. A run killed by the job timeout does none of those things.
    """
    deadline = time.monotonic() + minutes * 60
    appended = 0
    done = 0
    targets = needs_history(conn, budget)
    stopped = "drained"

    for i, nct_id in enumerate(targets, start=1):
        if time.monotonic() >= deadline:
            stopped = "deadline"
            break
        try:
            appended += land_history(conn, state, source, nct_id)
            done += 1
        except Exception as exc:  # noqa: BLE001
            # One unavailable record must not end the sweep. It is recorded and
            # retried on the next run, because it stays in needs_history().
            state.detail.setdefault("history_errors", []).append(f"{nct_id}: {exc!r}")
        if i % 50 == 0:
            conn.commit()
    else:
        if len(targets) == budget:
            stopped = "budget"

    conn.commit()
    state.note(
        history_requested=len(targets),
        history_completed=done,
        history_rows_appended=appended,
        history_budget=budget,
        history_minutes=minutes,
        history_stopped_on=stopped,
    )
    return appended


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embargo M0 collector")
    parser.add_argument("--job", choices=("daily", "backfill"), default="daily")
    parser.add_argument(
        "--since",
        type=dt.date.fromisoformat,
        default=None,
        help="collect postings on or after this date (default: 14 days ago, "
        "or the start of the census window for a backfill)",
    )
    parser.add_argument("--history-budget", type=int, default=DEFAULT_HISTORY_BUDGET)
    parser.add_argument(
        "--history-minutes",
        type=float,
        default=HISTORY_MINUTES,
        help="wall-clock box for the history sweep; this is what actually governs",
    )
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--skip-history", action="store_true", help="postings sweep only")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.since is not None:
        since = args.since
    elif args.job == "backfill":
        since = dt.date(CENSUS_START_YEAR, 1, 1)
    else:
        since = today_utc() - dt.timedelta(days=DAILY_LOOKBACK_DAYS)

    cfg = settings()
    with Http(
        user_agent=cfg.user_agent,
        min_interval_s=cfg.min_interval_s,
        max_retries=cfg.max_retries,
    ) as http:
        source = CtGov(http)
        with connect() as conn, run_log(conn, args.job, source=source) as state:
            appended = sweep_postings(conn, state, source, since, max_pages=args.max_pages)
            if not args.skip_history:
                appended += sweep_history(
                    conn, state, source, args.history_budget, args.history_minutes
                )
            state.rows_appended = appended
            state.http_calls = http.calls
            print(json.dumps({"run_id": state.run_id, **state.detail}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
