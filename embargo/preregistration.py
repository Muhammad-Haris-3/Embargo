"""Constants fixed by PREREGISTRATION.md.

Nothing in this module may be changed without an amendment appended to that
document. `tests/test_preregistration.py` parses the markdown table and asserts
every value here matches it, so drift in either direction fails the build.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

# --- freeze dates -----------------------------------------------------------
# The primary outcome is computed once, at this date, after all three gates pass.
PRIMARY_FREEZE_DATE: Final = dt.date(2024, 6, 30)

# Gate 3 runs at every step on this grid whose cohorts are mature.
FREEZE_GRID_START: Final = dt.date(2016, 6, 30)
FREEZE_GRID_STEP_MONTHS: Final = 12

# --- maturity ---------------------------------------------------------------
# Seven years. Set from the shape of the wait distribution, not convenience: an
# unweighted probe of 1,000 posted trials put p99 of the wait at 2,075 days, and
# the horizon has to sit beyond that with room to spare. That probe conditions
# on trials that posted, which over-selects long waits; M1 recomputes it by
# cohort, and a p99 beyond this value is an amendment, not an edit.
MATURITY_DAYS: Final = 3285

# --- gates ------------------------------------------------------------------
QUEUE_TOL: Final = 0.10  # relative, Gate 3
CENSUS_START_YEAR: Final = 2008  # Gate 2, inclusive
CENSUS_END_YEAR: Final = 2025  # Gate 2, inclusive
GATE1_SAMPLE_SIZE: Final = 200
GATE1_SEED: Final = 20260830
MIN_COHORT_COVERAGE: Final = 0.98

# --- secondary study: deadline drift ----------------------------------------
REPORTING_DEADLINE_MONTHS: Final = 12
DRIFT_IS_FORWARD_EDIT: Final = True

# --- conventions that decide boundary cases ---------------------------------
# Each of these could otherwise be chosen after seeing which way it moved the
# headline. See PREREGISTRATION.md for the reasoning behind all three.
PARTIAL_DATE_TO_MONTH_START: Final = True
NEGATIVE_WAIT_IS_ANOMALY: Final = True
ARITHMETIC: Final = "integer-days-utc"

# --- collection -------------------------------------------------------------
POLL_HOUR_UTC: Final = 7
