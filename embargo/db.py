"""Database access.

psycopg is an optional dependency. Everything in this project that can be
tested without a database is importable without one, so the offline suite runs
on a fresh clone with no services running.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings


class DatabaseUnavailable(RuntimeError):
    pass


def _psycopg():  # pragma: no cover - trivial import shim
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise DatabaseUnavailable(
            'psycopg is not installed. Install the pipeline extra: python -m pip install -e ".[db]"'
        ) from exc
    return psycopg


@contextmanager
def connect(dsn: str | None = None, *, admin: bool = False) -> Iterator[Any]:
    """Open a connection, committing on success and rolling back on error."""
    psycopg = _psycopg()
    cfg = settings()
    target = dsn or (cfg.admin_dsn if admin else cfg.dsn)
    conn = psycopg.connect(target, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def canonical_sha256(payload: Any) -> bytes:
    """A stable digest of a JSON payload.

    Sort keys and use compact separators, so a re-serialisation that reorders
    fields does not read as the record having changed. Insert-if-changed is only
    meaningful if "changed" is defined by content rather than by formatting.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).digest()
