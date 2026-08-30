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
from typing import Any

from .config import settings
from .ctgov import CtGov, status_dates
from .db import canonical_sha256, connect
from .http import Http
from .preregistration import CENSUS_START_YEAR
from .runlog import Run, run as run_log

# How far back a daily run looks. Generous on purpose: the sweep is
# insert-if-changed, so overlapping windows cost a little bandwidth and buy
# tolerance for a scheduler that missed a day.
DAILY_LOOKBACK_DAYS = 14

# History calls per run. One call per record, and there are tens of thousands of
# records, so the backlog is drained over days rather than in one burst against
# an undocumented endpoint.
DEFAULT_HISTORY_BUDGET = 400


def posted_since(since: dt.date) -> str:
    """Search term for records whose results were first posted on or after a date."""
    return f"AREA[ResultsFirstPostDate]RANGE[{since.isoformat()},MAX]"


def land_study(conn: Any, state: Run, study: dict[str, Any]) -> bool:
    """Insert a payload if this exact content has not been seen before."""
    dates = status_dates(study)
    nct_id = dates["nct_id"]
    if not nct_id:
        return False

    digest = canonical_sha256(study)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO landing_study (nct_id, content_sha256, ingest_run_id, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (nct_id, content_sha256) DO NOTHING
            """,
            (nct_id, digest, state.run_id, json.dumps(study, default=str)),
        )
        return cur.rowcount > 0


def land_history(conn: Any, state: Run, source: CtGov, nct_id: str) -> int:
    """Fetch and store a record revision list. Returns rows appended."""
    versions = source.history(nct_id)
    appended = 0
    with conn.cursor() as cur:
        for v in versions:
            cur.execute(
                """
                INSERT INTO record_versions
                    (nct_id, version, version_date, status, module_labels,
                     touched_results, ingest_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (nct_id, version) DO NOTHING
                """,
                (
                    v.nct_id,
                    v.version,
                    v.version_date,
                    v.status,
                    list(v.module_labels),
                    v.touched_results,
                    state.run_id,
                ),
            )
            appended += cur.rowcount
    return appended


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
    for study in source.search(query_term=posted_since(since), max_pages=max_pages):
        seen += 1
        if land_study(conn, state, study):
            appended += 1
        # Commit in batches. A long sweep that dies at page 40 should keep the
        # first 39 pages, because the alternative is a collector that can only
        # succeed completely and therefore, on a bad day, never.
        if seen % 500 == 0:
            conn.commit()
    conn.commit()
    state.note(postings_seen=seen, postings_appended=appended, since=since.isoformat())
    return appended


def sweep_history(conn: Any, state: Run, source: CtGov, budget: int) -> int:
    appended = 0
    targets = needs_history(conn, budget)
    for i, nct_id in enumerate(targets, start=1):
        try:
            appended += land_history(conn, state, source, nct_id)
        except Exception as exc:  # noqa: BLE001
            # One unavailable record must not end the sweep. It is recorded and
            # retried on the next run, because it stays in needs_history().
            state.detail.setdefault("history_errors", []).append(f"{nct_id}: {exc!r}")
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    state.note(
        history_requested=len(targets),
        history_rows_appended=appended,
        history_budget=budget,
        history_backlog_drained=len(targets) < budget,
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
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--skip-history", action="store_true", help="postings sweep only")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.since is not None:
        since = args.since
    elif args.job == "backfill":
        since = dt.date(CENSUS_START_YEAR, 1, 1)
    else:
        since = dt.date.today() - dt.timedelta(days=DAILY_LOOKBACK_DAYS)

    cfg = settings()
    with Http(
        user_agent=cfg.user_agent,
        min_interval_s=cfg.min_interval_s,
        max_retries=cfg.max_retries,
    ) as http:
        source = CtGov(http)
        with connect() as conn:
            with run_log(conn, args.job, source=source) as state:
                appended = sweep_postings(conn, state, source, since, max_pages=args.max_pages)
                if not args.skip_history:
                    appended += sweep_history(conn, state, source, args.history_budget)
                state.rows_appended = appended
                state.http_calls = http.calls
                print(json.dumps({"run_id": state.run_id, **state.detail}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
