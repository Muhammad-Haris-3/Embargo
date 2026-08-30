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

from .config import ROOT
from .db import connect

SQL_DIR = ROOT / "sql"


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

    # Roles and grants need ownership, so migration runs on the admin DSN. The
    # collector never does.
    with connect(admin=True) as conn:
        for path in paths:
            sql = path.read_text(encoding="utf-8")
            with conn.cursor() as cur:
                cur.execute(sql)
            print(f"applied {path.name}")
    print(f"{len(paths)} file(s) applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
