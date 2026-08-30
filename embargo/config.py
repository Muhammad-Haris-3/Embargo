"""Settings, read from the environment.

No framework, no magic. Every value has a default that works for a local run
against a local Postgres, so a fresh clone can do something without a .env.

The contact address in the user agent is not decoration. This project polls a
public API belonging to someone else; they are entitled to know who is calling
and to be able to ask us to stop.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> list[str]:
    """Populate os.environ from a .env file. Returns the names it set.

    Values already present in the environment win, so an explicitly exported
    variable is never silently overridden by a stale file.
    """
    path = path or ROOT / ".env"
    if not path.exists():
        return []

    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


@dataclass(frozen=True)
class Settings:
    dsn: str
    admin_dsn: str
    contact: str
    min_interval_s: float
    max_retries: int

    @property
    def user_agent(self) -> str:
        """Who we are, and what we are, in that order.

        Both halves are load-bearing. Measured 2026-08-30: the registry sits
        behind a filter that cross-checks the declared user agent against the
        client fingerprint, and a request that fingerprints as httpx while
        calling itself something else is refused with a 403 -- including, and
        this is the reassuring part, a browser-shaped string. A bare
        `python-httpx/x.y` is accepted but says nothing about who is calling.

        So the string states both: the project and its contact, and the library
        actually making the request. That is more accurate than either half
        alone, and it is the only combination observed to be both truthful and
        accepted. See Embargo_M0_Spec.md.
        """
        import httpx

        version = __import__("embargo").__version__
        return f"Embargo/{version} (+{self.contact}) python-httpx/{httpx.__version__}"


def settings() -> Settings:
    load_dotenv()
    return Settings(
        dsn=os.environ.get("EMBARGO_DSN", "postgresql://postgres:postgres@localhost:5432/embargo"),
        admin_dsn=os.environ.get(
            "EMBARGO_ADMIN_DSN",
            os.environ.get("EMBARGO_DSN", "postgresql://postgres:postgres@localhost:5432/embargo"),
        ),
        # Deliberately not a real address by default. A run that has not been
        # configured should identify itself as unconfigured rather than
        # impersonate a contactable operator.
        contact=os.environ.get("EMBARGO_CONTACT", "unconfigured-local-run"),
        min_interval_s=float(os.environ.get("EMBARGO_MIN_INTERVAL_S", "0.35")),
        max_retries=int(os.environ.get("EMBARGO_MAX_RETRIES", "5")),
    )
