"""The API must not be able to write.

`sql/003_roles.sql` gives `embargo_api` SELECT and nothing else, so the
guarantee is a grant. This file defends the step before that: which credential
the service picks up in the first place.

The failure it exists to prevent is quiet. Someone sets `EMBARGO_DSN` on the
API host -- the same variable name the collector uses, so it is the obvious
thing to paste -- and the service comes up, works perfectly, and holds INSERT
for the rest of its life.
"""

from __future__ import annotations

import pytest

from api.main import WritableCredentialInProduction, reader_dsn

READER = "postgresql://embargo_api:pw@host/neondb"
WRITER = "postgresql://embargo_app:pw@host/neondb"


class TestReaderDsn:
    def test_prefers_the_reader(self, monkeypatch):
        monkeypatch.setenv("EMBARGO_READER_DSN", READER)
        monkeypatch.setenv("EMBARGO_DSN", WRITER)
        assert reader_dsn() == READER

    def test_falls_back_locally(self, monkeypatch):
        """A developer with one database should not have to set two variables."""
        monkeypatch.delenv("EMBARGO_READER_DSN", raising=False)
        monkeypatch.delenv("EMBARGO_ENV", raising=False)
        monkeypatch.setenv("EMBARGO_DSN", WRITER)
        assert reader_dsn() == WRITER

    def test_refuses_to_fall_back_in_production(self, monkeypatch):
        """The whole point.

        If the API could reach for the collector's credential, the append-only
        guarantee would rest on this service never choosing to write.
        """
        monkeypatch.delenv("EMBARGO_READER_DSN", raising=False)
        monkeypatch.setenv("EMBARGO_ENV", "production")
        monkeypatch.setenv("EMBARGO_DSN", WRITER)
        with pytest.raises(WritableCredentialInProduction) as exc:
            reader_dsn()
        assert "EMBARGO_READER_DSN" in str(exc.value)

    def test_production_with_a_reader_is_fine(self, monkeypatch):
        monkeypatch.setenv("EMBARGO_ENV", "production")
        monkeypatch.setenv("EMBARGO_READER_DSN", READER)
        assert reader_dsn() == READER

    def test_nothing_configured_is_empty_not_an_exception(self, monkeypatch):
        """An unconfigured local run answers 503 from the caller, which is a
        clearer signal than a crash at import time."""
        monkeypatch.delenv("EMBARGO_READER_DSN", raising=False)
        monkeypatch.delenv("EMBARGO_DSN", raising=False)
        monkeypatch.delenv("EMBARGO_ENV", raising=False)
        assert reader_dsn() == ""


class TestDbFailuresAreLegible:
    """A misconfigured deployment must not look like a broken one.

    Every database-backed endpoint returned a bare 500 on the first deploy,
    because reader_dsn raises a RuntimeError and FastAPI renders that as
    "Internal Server Error" with no body. The message naming the missing
    variable never reached anyone.
    """

    def test_missing_credential_in_production_is_a_503_that_explains(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app

        monkeypatch.delenv("EMBARGO_READER_DSN", raising=False)
        monkeypatch.setenv("EMBARGO_ENV", "production")
        monkeypatch.setenv("EMBARGO_DSN", WRITER)

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/v1/status")
        assert r.status_code == 503
        assert "EMBARGO_READER_DSN" in r.json()["detail"]

    def test_nothing_configured_is_a_503_that_explains(self, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app

        monkeypatch.delenv("EMBARGO_READER_DSN", raising=False)
        monkeypatch.delenv("EMBARGO_DSN", raising=False)
        monkeypatch.delenv("EMBARGO_ENV", raising=False)

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/v1/gates")
        assert r.status_code == 503
        assert "EMBARGO_READER_DSN" in r.json()["detail"]

    def test_health_still_answers_without_a_database(self, monkeypatch):
        """The reason /health does not touch the database."""
        from fastapi.testclient import TestClient

        from api.main import app

        monkeypatch.delenv("EMBARGO_READER_DSN", raising=False)
        monkeypatch.delenv("EMBARGO_DSN", raising=False)
        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/health").status_code == 200
