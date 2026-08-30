"""M1: the wait, by submission cohort.

The M0 probe reported a median wait of about 100 days from a sample of records
posted since 2024. That number is wrong in a direction we can name, and this
module exists to replace it.

**Why the probe was biased.** Conditioning on records that posted in a recent
window over-selects long waits: a trial submitted in 2010 and posted in 2025 is
in the sample; one submitted in 2010 and posted in 2011 is not. The longer a
record waited, the likelier it is to have posted inside any recent window.

**Why cohorts fix that, and what they do not fix.** Grouping by the year of
submission removes the selection on posting date: every trial submitted in 2015
belongs to the 2015 cohort regardless of when it emerged. What it cannot remove
is the censoring, and the censoring runs the other way:

    A cohort's observed waits include only the trials that have posted by today.
    The ones still waiting are invisible -- that is the premise of this project.
    So a recent cohort shows only its fast members, and its median is biased
    DOWNWARD. The bias shrinks as a cohort ages and approaches zero once
    essentially all of it has resolved.

So the two biases point in opposite directions, and neither is a correction for
the other. Mature cohorts are reported as estimates of the wait. Immature ones
are reported, labelled, and must not be quoted as the wait for that year: they
are a lower bound on it.

No queue is estimated here. That is M4, and it happens after three gates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .clock import today_utc
from .config import ROOT
from .ctgov import status_dates, wait_days
from .db import connect
from .preregistration import MATURITY_DAYS

ARTIFACT = ROOT / "artifacts" / "wait_cohorts.json"


@dataclass
class Cohort:
    """One submission year."""

    year: int
    waits: list[int] = field(default_factory=list)
    negative: int = 0
    partial: int = 0

    def percentile(self, q: float) -> int | None:
        if not self.waits:
            return None
        ordered = sorted(self.waits)
        return ordered[min(len(ordered) - 1, int(len(ordered) * q))]

    def summary(self, today: dt.date) -> dict[str, Any]:
        # A cohort is mature when even its slowest plausible member has had time
        # to resolve. Measured from the END of the submission year, because a
        # trial submitted in December of that year had the least time of any.
        cohort_end = dt.date(self.year, 12, 31)
        age_days = (today - cohort_end).days
        mature = age_days >= MATURITY_DAYS

        ordered = sorted(self.waits)
        n = len(ordered)
        return {
            "year": self.year,
            "n_observed": n,
            "is_mature": mature,
            "age_days_since_cohort_end": age_days,
            "median_days": self.percentile(0.50),
            "p75_days": self.percentile(0.75),
            "p90_days": self.percentile(0.90),
            "p99_days": self.percentile(0.99),
            "max_days": ordered[-1] if ordered else None,
            "share_over_180d": round(sum(w > 180 for w in ordered) / n, 4) if n else None,
            "share_over_365d": round(sum(w > 365 for w in ordered) / n, 4) if n else None,
            "negative_waits_excluded": self.negative,
            "partial_dates_flagged": self.partial,
            # The denominator is not knowable. n_observed counts the trials from
            # this cohort that have posted; the ones still in review cannot be
            # seen or counted, which is the whole premise. n_observed is a lower
            # bound on the size of the cohort, never the size of it.
            "n_is_lower_bound": True,
            "quotable": mature,
        }


def build_cohorts(records: Iterable[dict[str, Any]]) -> dict[int, Cohort]:
    """Group waits by the year of submission.

    Records without both dates are skipped: a trial that has not posted has no
    observable wait, and inventing one -- by censoring at today, say -- would
    put a number where the project's entire point is that there is not one.
    """
    cohorts: dict[int, Cohort] = {}
    for record in records:
        submit = record.get("results_first_submit")
        if not submit:
            continue
        cohort = cohorts.setdefault(submit.year, Cohort(year=submit.year))
        if record.get("has_partial_date"):
            cohort.partial += 1

        wait = wait_days(record)
        if wait is None:
            continue
        if wait < 0:
            # Preregistered: excluded and counted, never clamped to zero,
            # because a clamp moves the median in a known direction.
            cohort.negative += 1
            continue
        cohort.waits.append(wait)
    return cohorts


def read_records(conn: Any) -> list[dict[str, Any]]:
    """The most recently captured payload for each trial."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (nct_id) payload
              FROM landing_study
             ORDER BY nct_id, captured_at DESC
            """
        )
        return [status_dates(row[0]) for row in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1: wait distribution by submission cohort")
    parser.add_argument("--out", type=Path, default=ARTIFACT)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="also write the cohorts to mart_wait_cohorts, which is what the API serves",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    today = today_utc()
    with connect() as conn:
        records = read_records(conn)
        cohorts = build_cohorts(records)
        summaries_for_mart = [cohorts[y].summary(today) for y in sorted(cohorts)]
        if args.publish:
            publish(conn, summaries_for_mart)
            conn.commit()

    cohorts = build_cohorts(records)
    summaries = [cohorts[y].summary(today) for y in sorted(cohorts)]
    mature_years = [s["year"] for s in summaries if s["is_mature"]]
    pooled_mature = sorted(w for y in mature_years for w in cohorts[y].waits)

    report = {
        "computed_at": dt.datetime.now(dt.UTC).isoformat(),
        "records_read": len(records),
        "records_with_a_wait": sum(len(c.waits) for c in cohorts.values()),
        "maturity_days": MATURITY_DAYS,
        "cohorts": summaries,
        "mature_pooled": {
            "cohort_years": mature_years,
            "n": len(pooled_mature),
            "median_days": pooled_mature[len(pooled_mature) // 2] if pooled_mature else None,
            "p90_days": pooled_mature[int(len(pooled_mature) * 0.90)] if pooled_mature else None,
            "share_over_365d": (
                round(sum(w > 365 for w in pooled_mature) / len(pooled_mature), 4)
                if pooled_mature
                else None
            ),
        },
        "READ_THIS": (
            "Immature cohorts show only the trials that have already posted, so "
            "their medians are biased DOWNWARD and are a lower bound on the wait "
            "for that year. They are not quotable. The M0 probe figure was biased "
            "in the opposite direction, by conditioning on a recent posting "
            "window. Neither corrects the other."
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"{'cohort':>7} {'n':>7} {'median':>7} {'p90':>7} {'>365d':>7}  quotable")
    for s in summaries:
        share = f"{s['share_over_365d']:.1%}" if s["share_over_365d"] is not None else "-"
        flag = "yes" if s["quotable"] else "no  <-- censored, lower bound"
        print(
            f"{s['year']:>7} {s['n_observed']:>7,} {s['median_days']!s:>7} "
            f"{s['p90_days']!s:>7} {share:>7}  {flag}"
        )

    m = report["mature_pooled"]
    print()
    if m["n"]:
        span = f"{mature_years[0]}-{mature_years[-1]}"
        print(f"mature cohorts {span}, pooled:")
        print(
            f"  n={m['n']:,}  median={m['median_days']}d  "
            f"p90={m['p90_days']}d  >365d={m['share_over_365d']:.1%}"
        )
    else:
        print("no mature cohorts yet")
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


def publish(conn: Any, summaries: list[dict[str, Any]]) -> int:
    """Write a cohort snapshot to the mart the API reads.

    One snapshot per call, stamped with a single `computed_at` so that a reader
    taking "the latest" gets a consistent set rather than a mixture of two runs.
    """
    stamp = dt.datetime.now(dt.UTC)
    rows = 0
    with conn.cursor() as cur:
        for s in summaries:
            cur.execute(
                """
                INSERT INTO mart_wait_cohorts
                    (computed_at, cohort_year, n_observed, is_mature, quotable,
                     median_days, p75_days, p90_days, p99_days, max_days,
                     share_over_180d, share_over_365d, negative_waits,
                     partial_dates, maturity_days)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (computed_at, cohort_year) DO NOTHING
                """,
                (
                    stamp,
                    s["year"],
                    s["n_observed"],
                    s["is_mature"],
                    s["quotable"],
                    s["median_days"],
                    s["p75_days"],
                    s["p90_days"],
                    s["p99_days"],
                    s["max_days"],
                    s["share_over_180d"],
                    s["share_over_365d"],
                    s["negative_waits_excluded"],
                    s["partial_dates_flagged"],
                    MATURITY_DAYS,
                ),
            )
            rows += cur.rowcount
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
