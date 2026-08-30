"""A throttled, retrying HTTP client.

One client, one rate limit, shared by every caller. ClinicalTrials.gov does not
publish a request-per-minute figure, so rather than encode a number that may be
wrong we throttle conservatively and back off on anything that looks like a
refusal.

Retries are on transport errors and on 429/5xx only. A 4xx that is not 429 is a
bug in our request and retrying it just asks the same wrong question again.
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx


class SourceError(RuntimeError):
    """The source refused or returned something we cannot use."""


class Http:
    def __init__(
        self,
        *,
        user_agent: str,
        min_interval_s: float = 0.35,
        max_retries: int = 5,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._min_interval_s = min_interval_s
        self._max_retries = max_retries
        self._last_call = 0.0
        self.calls = 0

    def _throttle(self) -> None:
        wait = self._min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def get_json(self, url: str, **params: Any) -> Any:
        last: Exception | None = None
        for attempt in range(self._max_retries):
            self._throttle()
            try:
                self.calls += 1
                r = self._client.get(url, params=params or None)
            except httpx.HTTPError as exc:
                last = exc
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    raise SourceError(f"404 {url}")
                if r.status_code != 429 and r.status_code < 500:
                    raise SourceError(f"{r.status_code} {url}: {r.text[:200]}")
                last = SourceError(f"{r.status_code} {url}")

            # Exponential backoff with jitter. The jitter matters: a scheduled
            # job that retries on a fixed schedule turns one failure into a
            # synchronised burst against a source that is already struggling.
            sleep = min(60.0, (2**attempt)) + random.uniform(0, 0.5)
            time.sleep(sleep)

        raise SourceError(f"giving up on {url} after {self._max_retries} attempts: {last}")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Http":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
