"""Today, in the timezone the project actually uses.

PREREGISTRATION.md fixes the arithmetic as `integer-days-utc`. The registry
advances its own data timestamp on a UTC day boundary, so a collector using the
machine local date would compute a different day -- and therefore a different
lookback window -- depending on where it happened to be running. In CI that is
UTC and the bug is invisible; on a developer laptop west of Greenwich it is off
by one for part of every day.
"""

from __future__ import annotations

import datetime as dt


def today_utc() -> dt.date:
    return dt.datetime.now(dt.UTC).date()
