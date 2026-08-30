"""Point-in-time reconstruction: what a record looked like on a past date.

The registry serves the record as it stands today. The history route serves the
record as it stood at any revision. Reconstruction is the join between them:
given a date, find the revision that was current on that date, and return it.

`version_current_on` is the whole idea, and it is deliberately small:

    the current revision on date D is the latest revision dated on or before D

Two things this does not do, both on purpose.

It does not interpolate. If a record's revisions are dated 2015-03-01 and
2016-09-14, then on 2016-01-01 the record looked exactly as it did in March
2015, because nobody had touched it. There is no intermediate state to invent.

It does not reach forward. A revision dated after the as-of date is refused by
the knowability guard rather than silently used, because a reconstruction that
quietly consults the future is worse than no reconstruction: it produces a
plausible number that cannot be told from a real one.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from .ctgov import CtGov
from .knowability import AsOf, NotKnowable

__all__ = ["NotKnowable", "record_as_of", "store_version", "version_current_on"]


def version_current_on(conn: Any, nct_id: str, as_of: AsOf) -> int | None:
    """The revision that was current on the as-of date, or None if none was.

    None means the record did not exist yet, which is a fact about the date and
    not an error.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT version
              FROM record_versions
             WHERE nct_id = %s
               AND version_date <= %s
             ORDER BY version_date DESC, version DESC
             LIMIT 1
            """,
            (nct_id, as_of.date),
        )
        row = cur.fetchone()
        return row[0] if row else None


def stored_version(conn: Any, nct_id: str, version: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT payload FROM version_payloads WHERE nct_id = %s AND version = %s",
            (nct_id, version),
        )
        row = cur.fetchone()
        return row[0] if row else None


def store_version(
    conn: Any, run_id: int, source: CtGov, nct_id: str, version: int
) -> dict[str, Any]:
    """Fetch a revision and keep it. Returns the payload.

    Cached on first sight. The history route is undocumented and may be
    withdrawn; a revision already stored is one we never have to ask for again,
    and reconstruction of a date we have already reconstructed must not depend
    on the endpoint still existing.
    """
    existing = stored_version(conn, nct_id, version)
    if existing is not None:
        return existing

    payload = source.version(nct_id, version)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO version_payloads (nct_id, version, ingest_run_id, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (nct_id, version) DO NOTHING
            """,
            (nct_id, version, run_id, json.dumps(payload, default=str)),
        )
    return payload


def record_as_of(
    conn: Any,
    nct_id: str,
    on: dt.date,
    *,
    source: CtGov | None = None,
    run_id: int | None = None,
) -> dict[str, Any] | None:
    """The record as it stood on a date.

    Served from the store when the revision is held. When it is not, and a
    source is supplied, it is fetched and kept; without a source the answer is
    None rather than a guess.
    """
    as_of = AsOf(on)
    version = version_current_on(conn, nct_id, as_of)
    if version is None:
        return None

    payload = stored_version(conn, nct_id, version)
    if payload is not None:
        return payload
    if source is None or run_id is None:
        return None
    return store_version(conn, run_id, source, nct_id, version)


def status_module_of(payload: dict[str, Any]) -> dict[str, Any]:
    """The status module of a record version, however the route nested it.

    A version fetched from the history route arrives wrapped in `study`; the
    same record from the documented API does not. Gate 1 compares the two, so
    the unwrapping happens in one place rather than at each call site.
    """
    record = payload.get("study", payload)
    return (record.get("protocolSection") or {}).get("statusModule") or {}
