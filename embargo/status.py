"""What has been collected, and on which days nothing was.

The M0 exit criterion is not "the collector works". It is seven consecutive
daily runs with no gap in the run log, and that has to be checkable by running
something rather than by reading a list of dates and believing it.

A day with no successful run is printed as a gap. Gaps are not recoverable: the
queue on a day nobody looked at is gone, and the whole project rests on the run
log being an honest record of when we looked.

Exit status is 0 when the required streak is met and 1 when it is not, so this
can gate a workflow.

Usage:
    python -m embargo.status
    python -m embargo.status --require-streak 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .clock import today_utc
from .db import connect

REQUIRED_STREAK = 7


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collection coverage and run log")
    parser.add_argument("--require-streak", type=int, default=REQUIRED_STREAK)
    parser.add_argument("--days", type=int, default=14, help="how far back to show")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    today = today_utc()
    window_start = today - dt.timedelta(days=args.days - 1)

    with connect() as conn, conn.cursor() as cur:
        # Collection began when the first run opened. Days before that are not
        # gaps: nothing was expected of them. A gap means a day we were supposed
        # to look and did not, and calling anything else a gap makes the real
        # ones easy to stop reading.
        cur.execute("SELECT min((started_at AT TIME ZONE 'UTC')::date) FROM ingest_runs")
        collection_start = cur.fetchone()[0]

        cur.execute("SELECT count(*), count(DISTINCT nct_id) FROM landing_study")
        land_rows, land_trials = cur.fetchone()
        cur.execute("SELECT count(*), count(DISTINCT nct_id) FROM record_versions")
        ver_rows, ver_trials = cur.fetchone()

        # A day counts only if a run finished ok on it. A run that started and
        # never closed is exactly the failure this is looking for.
        cur.execute(
            """
            SELECT (started_at AT TIME ZONE 'UTC')::date AS day,
                   count(*) FILTER (WHERE status = 'ok')      AS ok,
                   count(*) FILTER (WHERE status = 'failed')  AS failed,
                   count(*) FILTER (WHERE finished_at IS NULL) AS unclosed,
                   coalesce(sum(rows_appended), 0)            AS rows
              FROM ingest_runs
             WHERE job IN ('daily', 'backfill')
               AND (started_at AT TIME ZONE 'UTC')::date >= %s
             GROUP BY day
             ORDER BY day
            """,
            (window_start,),
        )
        by_day = {r[0]: r[1:] for r in cur.fetchall()}

    print(f"landing_study    {land_rows:>9,} rows / {land_trials:,} trials")
    print(f"record_versions  {ver_rows:>9,} rows / {ver_trials:,} trials historied")
    if collection_start is None:
        print()
        print("nothing has been collected yet")
        return 1
    print(
        f"collecting since {collection_start.isoformat()} ({(today - collection_start).days + 1} days)"
    )
    print()

    # Never report on days before there was a collector to miss them.
    window_start = max(window_start, collection_start)

    print(f"{'day (UTC)':<12} {'ok':>3} {'fail':>5} {'open':>5} {'rows':>9}")
    day = window_start
    while day <= today:
        stats = by_day.get(day)
        if stats is None:
            marker = "  <-- GAP, not recoverable" if day < today else "  (today, not yet run)"
            print(f"{day.isoformat():<12} {'-':>3} {'-':>5} {'-':>5} {'-':>9}{marker}")
        else:
            ok, failed, unclosed, rows = stats
            flag = "  <-- run never closed" if unclosed else ""
            print(f"{day.isoformat():<12} {ok:>3} {failed:>5} {unclosed:>5} {rows:>9,}{flag}")
        day += dt.timedelta(days=1)

    # The streak counts back from yesterday: today's scheduled run may not have
    # happened yet, and counting it as a gap would make the check fail every
    # morning before 07:00 UTC.
    streak = 0
    day = today - dt.timedelta(days=1)
    while by_day.get(day) and by_day[day][0] > 0:
        streak += 1
        day -= dt.timedelta(days=1)

    print()
    print(f"consecutive days with a successful run, ending yesterday: {streak}")
    if streak >= args.require_streak:
        print(f"M0 coverage criterion MET ({args.require_streak} required)")
        return 0
    print(f"M0 coverage criterion NOT met -- {args.require_streak} required, {streak} so far")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
