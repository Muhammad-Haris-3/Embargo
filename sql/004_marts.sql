-- Embargo, layer 4: marts.
--
-- The API serves rows and never computes. A request that triggered an
-- estimation would make the figure depend on when it was asked for, and would
-- put a statistical method inside a 512 MB web container on someone else's
-- schedule.
--
-- Marts are append-only like everything else. There is no refresh-in-place,
-- because the writer role holds INSERT and nothing else: a recomputation is a
-- new snapshot stamped with the moment it was computed, and readers take the
-- latest. That also means a figure the site once served can always be found
-- again, which a mutable mart cannot promise.

BEGIN;

CREATE TABLE IF NOT EXISTS mart_wait_cohorts (
    computed_at      timestamptz NOT NULL DEFAULT now(),
    cohort_year      integer     NOT NULL,
    n_observed       integer     NOT NULL,
    is_mature        boolean     NOT NULL,
    -- Quotable is not a synonym for mature; it is the editorial consequence of
    -- it, carried into the data so that a consumer cannot pick up an immature
    -- median without also picking up the reason it must not be quoted.
    quotable         boolean     NOT NULL,
    median_days      integer,
    p75_days         integer,
    p90_days         integer,
    p99_days         integer,
    max_days         integer,
    share_over_180d  numeric,
    share_over_365d  numeric,
    negative_waits   integer     NOT NULL DEFAULT 0,
    partial_dates    integer     NOT NULL DEFAULT 0,
    maturity_days    integer     NOT NULL,

    PRIMARY KEY (computed_at, cohort_year),
    CONSTRAINT n_observed_non_negative CHECK (n_observed >= 0)
);

CREATE INDEX IF NOT EXISTS mart_wait_cohorts_latest
    ON mart_wait_cohorts (computed_at DESC, cohort_year);

COMMIT;
