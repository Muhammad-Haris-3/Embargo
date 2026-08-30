-- Embargo, layer 2: the commitment register.
--
-- The queue is not observable on the day it exists. Every number this project
-- publishes about it is therefore an estimate, and an estimate that can be
-- revised after the truth arrives is worth nothing.
--
-- So estimates are committed here, before the truth exists, and graded later
-- from a separate table. The writer role holds INSERT and nothing else -- see
-- 003_roles.sql -- so "we did not change it afterwards" is a property of the
-- database rather than a promise made by careful code.

BEGIN;

-- An estimate of the queue at a freeze date, committed before it can be marked.
CREATE TABLE IF NOT EXISTS queue_estimates (
    estimate_id      bigserial   PRIMARY KEY,
    committed_at     timestamptz NOT NULL DEFAULT now(),
    freeze_date      date        NOT NULL,
    -- The estimator, identified well enough that a later reader can tell
    -- whether two estimates came from the same method.
    method           text        NOT NULL,
    method_sha256    bytea       NOT NULL,
    -- The estimate itself, and the interval around it.
    q_hat            numeric     NOT NULL,
    ci_low           numeric,
    ci_high          numeric,
    -- A digest of the exact input rows, so a rerun that claims to reproduce an
    -- estimate can be checked rather than believed.
    inputs_sha256    bytea       NOT NULL,
    ingest_run_id    bigint      NOT NULL REFERENCES ingest_runs(run_id),
    detail           jsonb       NOT NULL DEFAULT '{}'::jsonb,

    -- An estimate is made FOR a past date, FROM a later vantage point. The
    -- reverse -- committing an estimate for a date that has not happened, from
    -- data that therefore cannot exist -- is the cheapest way to fake this
    -- project, and it is unavailable.
    CONSTRAINT estimate_after_freeze CHECK (committed_at::date >= freeze_date),
    CONSTRAINT q_hat_non_negative CHECK (q_hat >= 0)
);

CREATE INDEX IF NOT EXISTS queue_estimates_freeze ON queue_estimates (freeze_date);

-- The realised queue at a freeze date, computed from records that have since
-- disclosed both of their dates.
--
-- This is a LOWER BOUND and the column names say so. A trial submitted before
-- the freeze date that has still not posted is invisible today exactly as it
-- was invisible then. The bound tightens as postings arrive.
CREATE TABLE IF NOT EXISTS queue_realised (
    freeze_date      date        NOT NULL,
    computed_at      timestamptz NOT NULL DEFAULT now(),
    q_star_lower     integer     NOT NULL,
    -- How much of the relevant cohort has had time to resolve, so that a
    -- tightening bound is never mistaken for a growing queue.
    cohort_coverage  numeric     NOT NULL,
    is_mature        boolean     NOT NULL,
    ingest_run_id    bigint      NOT NULL REFERENCES ingest_runs(run_id),

    PRIMARY KEY (freeze_date, computed_at),
    CONSTRAINT q_star_non_negative CHECK (q_star_lower >= 0)
);

-- Results of the preregistered gates. Recorded, not asserted in prose.
CREATE TABLE IF NOT EXISTS gate_results (
    gate             text        NOT NULL,   -- 'capture_faithful' | 'census_agrees' | 'estimator_recovers'
    checked_at       timestamptz NOT NULL DEFAULT now(),
    passed           boolean     NOT NULL,
    n_checked        integer     NOT NULL,
    n_failed         integer     NOT NULL,
    worst_diff       numeric,
    detail           jsonb       NOT NULL DEFAULT '{}'::jsonb,

    PRIMARY KEY (gate, checked_at)
);

COMMIT;
