"""The run log.

Every execution of every job opens a row here and closes it, whether it
succeeded or not. This is not operational hygiene, it is evidence: the project
claims things about what the registry looked like on particular days, and those
claims are only as good as the record of which days we actually looked.

A failed run is written as failed. A run that never finishes leaves a row with
no `finished_at`, which is exactly what a silently dead scheduled job should
look like from the outside.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Run:
    run_id: int
    job: str
    rows_appended: int = 0
    http_calls: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def note(self, **facts: Any) -> None:
        self.detail.update(facts)


@contextmanager
def run(conn: Any, job: str, *, source: Any | None = None) -> Iterator[Run]:
    """Open a run, and close it however it ends.

    `source`, when given, is asked for the registry data timestamp before the
    job starts. That single call is what distinguishes "the registry published
    nothing new today" from "our collector has been talking to a frozen mirror
    for a week".
    """
    data_timestamp: dt.datetime | None = None
    api_version: str | None = None
    timestamp_error: str | None = None
    if source is not None:
        try:
            meta = source.data_timestamp()
            api_version = meta.get("apiVersion")
            raw = meta.get("dataTimestamp")
            if raw:
                data_timestamp = dt.datetime.fromisoformat(raw)
        except Exception as exc:  # noqa: BLE001 - a missing timestamp must not stop a run
            # Recorded rather than swallowed. A run whose freshness check failed
            # is still a run worth having, but a week of them is a source
            # problem, and a silent except would hide exactly that.
            timestamp_error = repr(exc)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_runs (job, data_timestamp, api_version)
            VALUES (%s, %s, %s)
            RETURNING run_id
            """,
            (job, data_timestamp, api_version),
        )
        run_id = cur.fetchone()[0]
    conn.commit()

    state = Run(run_id=run_id, job=job)
    if timestamp_error:
        state.note(data_timestamp_error=timestamp_error)
    try:
        yield state
    except Exception as exc:
        conn.rollback()
        _close(conn, state, "failed", error=repr(exc))
        raise
    else:
        _close(conn, state, "ok")


def _close(conn: Any, state: Run, status: str, **extra: Any) -> None:
    detail = dict(state.detail)
    detail.update(extra)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE ingest_runs
               SET finished_at = now(),
                   status = %s,
                   rows_appended = %s,
                   http_calls = %s,
                   detail = %s::jsonb
             WHERE run_id = %s
            """,
            (
                status,
                state.rows_appended,
                state.http_calls,
                json.dumps(detail, default=str),
                state.run_id,
            ),
        )
    conn.commit()
