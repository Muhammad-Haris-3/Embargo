"""The append-only guarantee, actually attempted.

A test suite that never tries the forbidden write proves nothing. These tests
connect **as embargo_writer** -- not as the owner, not as a superuser, both of
which bypass grants and would make every assertion here pass while guaranteeing
nothing -- and assert that UPDATE and DELETE raise.

They skip without a writer DSN, so the offline suite still runs on a fresh
clone. CI sets the DSN, and the workflow additionally fails if these skip:
a guarantee that quietly went untested is the failure mode this file exists to
prevent.
"""

from __future__ import annotations

import os

import pytest

psycopg = pytest.importorskip("psycopg")

WRITER_DSN = os.environ.get("EMBARGO_WRITER_DSN")

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not WRITER_DSN, reason="EMBARGO_WRITER_DSN is unset"),
]


@pytest.fixture()
def writer():
    conn = psycopg.connect(WRITER_DSN, autocommit=True)
    yield conn
    conn.close()


@pytest.fixture()
def a_run(writer):
    """A run row to hang foreign keys from."""
    with writer.cursor() as cur:
        cur.execute("INSERT INTO ingest_runs (job) VALUES ('test') RETURNING run_id")
        return cur.fetchone()[0]


def test_the_role_is_not_a_superuser(writer):
    """If this fails, every other assertion in the file is worthless."""
    with writer.cursor() as cur:
        cur.execute("SELECT current_user, usesuper FROM pg_user WHERE usename = current_user")
        user, is_super = cur.fetchone()
    assert not is_super, f"{user} is a superuser; grants do not apply to it"


def test_writer_can_append_an_observation(writer, a_run):
    with writer.cursor() as cur:
        cur.execute(
            """
            INSERT INTO landing_study (nct_id, content_sha256, ingest_run_id, payload)
            VALUES ('NCT00000001', %s, %s, '{}'::jsonb)
            ON CONFLICT DO NOTHING
            """,
            (b"\x01" * 32, a_run),
        )


def test_writer_cannot_restate_an_observation(writer):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with writer.cursor() as cur:
            cur.execute("UPDATE landing_study SET payload = '{}'::jsonb")


def test_writer_cannot_delete_an_observation(writer):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with writer.cursor() as cur:
            cur.execute("DELETE FROM landing_study")


def test_writer_cannot_rewrite_a_record_version(writer):
    """A version describes the past. It can never legitimately change."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with writer.cursor() as cur:
            cur.execute("UPDATE record_versions SET version_date = now()::date")


def test_writer_cannot_withdraw_a_committed_estimate(writer):
    """The point of the register.

    An estimate that can be deleted after the truth arrives is not a
    commitment, and Gate 3 would be unfalsifiable.
    """
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with writer.cursor() as cur:
            cur.execute("DELETE FROM queue_estimates")


def test_writer_cannot_amend_a_committed_estimate(writer):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with writer.cursor() as cur:
            cur.execute("UPDATE queue_estimates SET q_hat = 0")


def test_writer_cannot_rewrite_a_gate_result(writer):
    """A failed gate stays failed."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with writer.cursor() as cur:
            cur.execute("UPDATE gate_results SET passed = true")


def test_an_estimate_cannot_be_committed_for_a_future_freeze_date(writer, a_run):
    """Backdating, the cheapest way to fake this project.

    Committing an estimate for a date that has not happened, from data that
    therefore cannot exist, is refused by a CHECK rather than by review.
    """
    with pytest.raises(psycopg.errors.CheckViolation):
        with writer.cursor() as cur:
            cur.execute(
                """
                INSERT INTO queue_estimates
                    (freeze_date, method, method_sha256, q_hat, inputs_sha256, ingest_run_id)
                VALUES (now()::date + 30, 'test', %s, 1, %s, %s)
                """,
                (b"\x00" * 32, b"\x00" * 32, a_run),
            )


def test_run_log_may_be_closed(writer, a_run):
    """The one permitted UPDATE, and it holds no evidence.

    A run row records that we looked and how it went, never what we found.
    """
    with writer.cursor() as cur:
        cur.execute(
            "UPDATE ingest_runs SET status = 'ok', finished_at = now() WHERE run_id = %s",
            (a_run,),
        )
