"""Provision a fresh database, once.

`sql/003_roles.sql` creates `embargo_writer` and `embargo_reader` as NOLOGIN
group roles. They carry the grants and nothing connects as them. What a
deployment also needs is two *login* roles that are members of those groups, and
those need passwords, which do not belong in a file committed to a public repo.

So they are created here, with passwords generated locally at provisioning time.
Nothing is written to disk and nothing is sent anywhere: the two connection
strings are printed once, on your terminal, for you to paste into your secret
store. If you lose them, run again with --rotate.

Usage, against a database that already exists:

    python -m embargo.bootstrap --admin-dsn "postgresql://OWNER:PW@HOST/embargo?sslmode=require"

Run it as the database owner. On Neon that is the role the console created for
you -- typically `neondb_owner` -- because creating roles and altering default
privileges both require ownership.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from urllib.parse import quote, urlsplit, urlunsplit

from psycopg import sql

from .db import connect
from .migrate import main as migrate_main

WRITER_LOGIN = "embargo_app"
READER_LOGIN = "embargo_api"


def generate_password() -> str:
    """A password long enough that nobody is tempted to remember it."""
    return secrets.token_urlsafe(32)


def ensure_login_role(conn, name: str, group: str, password: str, *, rotate: bool) -> str:
    """Create a login role in a group, or rotate its password. Returns the action.

    CREATE ROLE and ALTER ROLE are utility statements, and Postgres does not
    accept bound parameters in them -- `PASSWORD %s` is a syntax error at the
    placeholder, not a value that fails to bind. The password therefore has to
    be part of the statement text, which is exactly the situation that invites
    an f-string and a quoting bug.

    psycopg.sql composes it instead: Identifier quotes the names, Literal quotes
    and escapes the password. Neither is string formatting, and neither can be
    talked out of escaping by the contents.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
        exists = cur.fetchone() is not None

        if exists and not rotate:
            return "unchanged"

        verb = "ALTER" if exists else "CREATE"
        cur.execute(
            sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.SQL(verb), sql.Identifier(name), sql.Literal(password)
            )
        )
        action = "rotated" if exists else "created"

        # Membership is what carries the grants. The login role itself is given
        # no privileges of its own, so revoking the membership is enough to cut
        # off access without dropping anything.
        cur.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(name)))
        return action


def dsn_for(admin_dsn: str, user: str, password: str) -> str:
    """Rewrite an admin DSN to point at a different role."""
    parts = urlsplit(admin_dsn)
    host = parts.hostname or "localhost"
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision Embargo roles on a fresh database")
    parser.add_argument(
        "--admin-dsn",
        required=True,
        help="owner connection string; used for this run only and never stored",
    )
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="reset the passwords of login roles that already exist",
    )
    parser.add_argument(
        "--skip-migrate", action="store_true", help="assume the schema is already applied"
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if not args.skip_migrate:
        # migrate reads the admin DSN from the environment, so hand it over for
        # this process only rather than asking for it twice.
        os.environ["EMBARGO_ADMIN_DSN"] = args.admin_dsn
        if migrate_main([]) != 0:
            return 1

    writer_pw, reader_pw = generate_password(), generate_password()
    with connect(args.admin_dsn) as conn:
        writer_action = ensure_login_role(
            conn, WRITER_LOGIN, "embargo_writer", writer_pw, rotate=args.rotate
        )
        reader_action = ensure_login_role(
            conn, READER_LOGIN, "embargo_reader", reader_pw, rotate=args.rotate
        )

    print(f"\n{WRITER_LOGIN}: {writer_action}")
    print(f"{READER_LOGIN}: {reader_action}")

    if "unchanged" in (writer_action, reader_action):
        print(
            "\nOne or both roles already existed and their passwords were left alone.\n"
            "Re-run with --rotate if you need new connection strings."
        )

    if writer_action != "unchanged":
        print("\n--- set as the EMBARGO_DSN secret (the collector) ---")
        print(dsn_for(args.admin_dsn, WRITER_LOGIN, writer_pw))
    if reader_action != "unchanged":
        print("\n--- set as the EMBARGO_READER_DSN secret (the API, from M5) ---")
        print(dsn_for(args.admin_dsn, READER_LOGIN, reader_pw))

    print(
        "\nThese are secrets and they are printed once. They are not written to\n"
        "disk by this script. Do not paste them into a file this repository\n"
        "tracks -- .env is gitignored, GitHub secrets are the deployment path.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
