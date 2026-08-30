"""The guard that makes point-in-time claims checkable.

Every claim this project makes about a past date is a claim about what was
knowable on it. That kind of claim fails silently: a computation that reaches
for a value dated after its own as-of date produces a perfectly plausible
number, and nothing about the output says it was impossible.

So the reach is made to raise instead. `AsOf` wraps a date and every value that
enters a point-in-time computation passes through it. A value dated later than
the as-of date is not a smaller number or a worse estimate -- it is evidence
from the future, and the computation stops.

This is the same failure GridCast calls lookahead leakage, and the same answer:
a guard that raises, exercised by tests that deliberately try to leak.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


class NotKnowable(RuntimeError):
    """A point-in-time computation reached for something that did not exist yet."""


@dataclass(frozen=True)
class AsOf:
    """A vantage point in time, and the authority on what it could see.

    Construct one for the date being reconstructed and route every dated value
    through it. Nothing in this project should compare dates to an as-of date by
    hand: the comparison is easy, remembering to write it is not.
    """

    date: dt.date

    def knows(self, value_date: dt.date | None) -> bool:
        """Could a value bearing this date have been held on the as-of date?"""
        if value_date is None:
            return True  # an absent value carries no information from the future
        return value_date <= self.date

    def require(self, value_date: dt.date | None, what: str) -> dt.date | None:
        """Return the date, or raise if it postdates the vantage point."""
        if not self.knows(value_date):
            raise NotKnowable(
                f"{what} is dated {value_date}, which is after the as-of date "
                f"{self.date}; it could not have been known"
            )
        return value_date

    def observable(self, records: Iterable[dict[str, Any]], *, posted: str = "results_first_post"):
        """The records whose results had been posted by the as-of date.

        This is the observability rule of the whole project, in one place. A
        trial that had not posted by `date` was, on that day, indistinguishable
        from one that never submitted anything -- so it is not in the set, and
        neither is its submission date, however plainly both are visible now.
        """
        for record in records:
            post = record.get(posted)
            if post is not None and post <= self.date:
                yield record

    def elapsed(self, since: dt.date) -> int:
        """Whole days from a past date to the vantage point."""
        self.require(since, "start date")
        return (self.date - since).days
