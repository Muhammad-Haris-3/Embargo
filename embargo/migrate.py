"""Apply the schema.

Every file in sql/ is idempotent by construction -- CREATE TABLE IF NOT EXISTS,
grants that can be reapplied, a DO block that creates roles only when absent --
so migration is simply "run them all, in order". A second run must produce no
change, and the M0 exit criteria require that to be demonstrated rather than
assumed.

Usage:
    python -m embargo.migrate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import ROOT, settings
from .db import connect

SQL_DIR = ROOT / "sql"

NO_OWNER_CREDENTIAL = """EMBARGO_ADMIN_DSN is not set, so migration would run as the collector role,
which owns nothing.

Migration needs the database owner connection string -- the one the Neon
console gives you, starting postgresql://neondb_owner: -- and it is
deliberately not kept in .env, because the collector must never hold a
credential that can UPDATE or DELETE.

PowerShell, for this session only:

  $env:EMBARGO_ADMIN_DSN = "postgresql://neondb_owner:PW@HOST/neondb?sslmode=require&channel_binding=require"
  python -m embargo.migrate
"""


def files() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the Embargo schema")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list the files that would be applied, without connecting",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    paths = files()
    if not paths:
        print(f"no .sql files in {SQL_DIR}", file=sys.stderr)
        return 1

    if args.dry_run:
        for path in paths:
            print(f"would apply {path.name}")
        return 0

    # Migration needs ownership, and EMBARGO_ADMIN_DSN falls back to EMBARGO_DSN
    # when it is unset. A missing owner credential therefore arrives as
    # "permission denied for schema public" on the FIRST file, which reads as
    # though the whole schema is broken when in fact only the newest file is
    # unapplied. Say what is actually wrong, before touching anything.
    cfg = settings()
    if cfg.admin_dsn == cfg.dsn:
        print(NO_OWNER_CREDENTIAL, file=sys.stderr)
        return 2

    with connect(admin=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user, has_schema_privilege(current_user, 'public', 'CREATE')"
            )
            who, may_create = cur.fetchone()
        if not may_create:
            print(
                f"Connected as {who}, which cannot CREATE in schema public. "
                "EMBARGO_ADMIN_DSN is set, but not to the owner.",
                file=sys.stderr,
            )
            return 2

        for path in paths:
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
            print(f"applied {path.name}")

    print(f"{len(paths)} file(s) applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
