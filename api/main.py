"""The read-only API.

It serves rows and it does not compute. Estimation runs offline, in scheduled
jobs, against the whole warehouse; a request that triggered it would make the
answer depend on when it was asked for and would put a statistical method
inside a small container on a stranger's schedule.

The role it connects as holds `SELECT` and nothing else, so "read-only" is a
database grant rather than a convention this module is trusted to keep.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .gating import gates_from_rows

app = FastAPI(
    title="Embargo",
    version="0.1.0",
    description=(
        "Measuring the gap between a clinical trial result existing and being "
        "readable. Read-only. Serves precomputed rows and never estimates at "
        "request time."
    ),
)


class WritableCredentialInProduction(RuntimeError):
    """The API was given a credential that can write."""


def reader_dsn() -> str:
    """The read-only connection string.

    In production this refuses to fall back to `EMBARGO_DSN`. That variable
    belongs to the collector and holds `INSERT`; if this service could reach for
    it, the append-only guarantee would rest on the API never *choosing* to
    write, rather than on its being unable to. Locally the fallback is a
    convenience, because there the only database is a developer's own.
    """
    reader = os.environ.get("EMBARGO_READER_DSN")
    if reader:
        return reader
    if os.environ.get("EMBARGO_ENV") == "production":
        raise WritableCredentialInProduction(
            "EMBARGO_READER_DSN is unset. The API will not fall back to "
            "EMBARGO_DSN in production: that role can INSERT, and this service "
            "must not be able to write. Set EMBARGO_READER_DSN to the "
            "embargo_api role."
        )
    return os.environ.get("EMBARGO_DSN", "")


@contextmanager
def db() -> Iterator[Any]:
    import psycopg

    dsn = reader_dsn()
    if not dsn:
        raise HTTPException(status_code=503, detail="no database configured")
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def rows(conn: Any, sql: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


@app.get("/health")
def health() -> dict[str, Any]:
    """Liveness only, and deliberately no database.

    A health check that touches the database reports the database, and a
    container that cannot answer at all is a different failure from one whose
    warehouse is unreachable.
    """
    return {"status": "ok", "service": "embargo"}


@app.get("/v1/status")
def status() -> dict[str, Any]:
    with db() as conn:
        counts = rows(
            conn,
            """
            SELECT (SELECT count(*) FROM landing_study),
                   (SELECT count(DISTINCT nct_id) FROM landing_study),
                   (SELECT count(*) FROM record_versions),
                   (SELECT count(*) FROM version_payloads),
                   (SELECT count(*) FROM queue_estimates)
            """,
        )[0]
        last = rows(
            conn,
            """
            SELECT job, status, started_at, finished_at, rows_appended, data_timestamp
              FROM ingest_runs
             WHERE job IN ('daily', 'backfill')
             ORDER BY started_at DESC
             LIMIT 1
            """,
        )
        gating = gates_from_rows(
            rows(conn, "SELECT gate, passed, checked_at FROM gate_results ORDER BY checked_at DESC")
        )

    run = last[0] if last else None
    return {
        "landing_rows": counts[0],
        "trials": counts[1],
        "record_versions": counts[2],
        "version_payloads": counts[3],
        "estimates_committed": counts[4],
        "last_collection": (
            {
                "job": run[0],
                "status": run[1],
                "started_at": run[2],
                "finished_at": run[3],
                "rows_appended": run[4],
                "registry_data_timestamp": run[5],
            }
            if run
            else None
        ),
        "primary_outcome_publishable": gating.publishable,
        "readonly_role_in_use": True,
    }


@app.get("/v1/gates")
def gates() -> dict[str, Any]:
    """Every gate's latest verdict, and the consequence of it."""
    with db() as conn:
        latest = rows(
            conn,
            """
            SELECT DISTINCT ON (gate) gate, passed, n_checked, n_failed, worst_diff, checked_at
              FROM gate_results
             ORDER BY gate, checked_at DESC
            """,
        )
        gating = gates_from_rows([(r[0], r[1], r[5]) for r in latest])

    return {
        "gates": [
            {
                "gate": r[0],
                "passed": r[1],
                "n_checked": r[2],
                "n_failed": r[3],
                "worst_diff": float(r[4]) if r[4] is not None else None,
                "checked_at": r[5],
            }
            for r in latest
        ],
        "publishable": gating.publishable,
        "failing": list(gating.failing),
        "never_run": list(gating.missing),
        "reason": gating.reason,
    }


@app.get("/v1/waits/cohorts")
def wait_cohorts() -> dict[str, Any]:
    """The wait by submission cohort, from the latest published snapshot.

    `quotable` travels with every row. An immature cohort shows only the trials
    that have already posted, so its median is a lower bound on the wait for
    that year, and a consumer must not be able to pick up the number without
    also picking up the reason.
    """
    with db() as conn:
        # A mart that has not been created yet is a deployment state, not a
        # server fault. Letting the driver's UndefinedTable become a 500 would
        # report a bug in this service for a migration nobody has run.
        import psycopg

        try:
            latest = rows(conn, "SELECT max(computed_at) FROM mart_wait_cohorts")[0][0]
        except psycopg.errors.UndefinedTable as exc:
            raise HTTPException(
                status_code=503,
                detail="mart_wait_cohorts does not exist; apply sql/004_marts.sql",
            ) from exc
        if latest is None:
            raise HTTPException(
                status_code=503,
                detail="no cohort snapshot has been published yet; run embargo.waits --publish",
            )
        data = rows(
            conn,
            """
            SELECT cohort_year, n_observed, is_mature, quotable, median_days,
                   p75_days, p90_days, p99_days, max_days, share_over_180d,
                   share_over_365d, negative_waits, partial_dates, maturity_days
              FROM mart_wait_cohorts
             WHERE computed_at = %s
             ORDER BY cohort_year
            """,
            (latest,),
        )

    return {
        "computed_at": latest,
        "maturity_days": data[0][13] if data else None,
        "cohorts": [
            {
                "year": r[0],
                "n_observed": r[1],
                "n_is_lower_bound": True,
                "is_mature": r[2],
                "quotable": r[3],
                "median_days": r[4],
                "p75_days": r[5],
                "p90_days": r[6],
                "p99_days": r[7],
                "max_days": r[8],
                "share_over_180d": float(r[9]) if r[9] is not None else None,
                "share_over_365d": float(r[10]) if r[10] is not None else None,
                "negative_waits_excluded": r[11],
                "partial_dates_flagged": r[12],
            }
            for r in data
        ],
    }


@app.get("/v1/queue/register")
def queue_register() -> dict[str, Any]:
    """Every estimate ever committed, with the bound it was later marked against.

    Including the ones that failed. A register holding only the estimates that
    turned out well answers a different question than the one asked.
    """
    with db() as conn:
        estimates = rows(
            conn,
            """
            SELECT DISTINCT ON (freeze_date)
                   freeze_date, q_hat, committed_at, method, detail
              FROM queue_estimates
             ORDER BY freeze_date, committed_at DESC
            """,
        )
        realised = {
            r[0]: (r[1], r[2])
            for r in rows(
                conn,
                """
                SELECT DISTINCT ON (freeze_date) freeze_date, q_star_lower, is_mature
                  FROM queue_realised
                 ORDER BY freeze_date, computed_at DESC
                """,
            )
        }

    points = []
    for freeze_date, q_hat, committed_at, method, detail in estimates:
        star, mature = realised.get(freeze_date, (None, None))
        q = float(q_hat)
        points.append(
            {
                "freeze_date": freeze_date,
                "q_hat": q,
                "q_star_lower": star,
                "q_star_is_a_lower_bound": True,
                "relative_error": round((q - star) / star, 4) if star else None,
                "is_mature": mature,
                "committed_at": committed_at,
                "method": method,
                "detail": detail,
            }
        )
    return {"points": points}


@app.get("/v1/queue/current")
def queue_current() -> JSONResponse:
    """How many results are in the queue today.

    This is the primary outcome, and it is withheld. `PREREGISTRATION.md`
    requires all three gates to pass before any queue estimate is published,
    and Gate 3 fails.

    The endpoint exists and refuses, rather than not existing. A missing route
    looks like an unfinished feature; a 409 that names the failing gate is the
    preregistration doing its job in public.
    """
    with db() as conn:
        gating = gates_from_rows(
            rows(conn, "SELECT gate, passed, checked_at FROM gate_results ORDER BY checked_at DESC")
        )

    if not gating.publishable:
        return JSONResponse(
            status_code=409,
            content={
                "published": False,
                "reason": gating.reason,
                "failing": list(gating.failing),
                "never_run": list(gating.missing),
                "see": "Embargo_M4_Summary.md",
            },
        )

    raise HTTPException(
        status_code=501,
        detail=(
            "All gates pass, and the current-queue figure has not been "
            "implemented yet. It must not be added without an entry in "
            "PREREGISTRATION.md describing what is being published."
        ),
    )


@app.get("/v1/coverage")
def coverage() -> dict[str, Any]:
    """Collection days, so a gap can be seen rather than inferred."""
    with db() as conn:
        data = rows(
            conn,
            """
            SELECT (started_at AT TIME ZONE 'UTC')::date AS day,
                   count(*) FILTER (WHERE status = 'ok'),
                   count(*) FILTER (WHERE status = 'failed'),
                   count(*) FILTER (WHERE finished_at IS NULL),
                   coalesce(sum(rows_appended), 0)
              FROM ingest_runs
             WHERE job IN ('daily', 'backfill')
             GROUP BY day
             ORDER BY day DESC
             LIMIT 60
            """,
        )
    return {
        "days": [
            {
                "day": r[0],
                "ok": r[1],
                "failed": r[2],
                "unclosed": r[3],
                "rows_appended": r[4],
            }
            for r in data
        ],
        "note": (
            "A day absent from this list is a day nothing ran. Gaps are not "
            "recoverable: the queue on a day nobody looked at is gone."
        ),
        "generated_at": dt.datetime.now(dt.UTC),
    }
