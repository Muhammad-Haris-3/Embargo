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
