-- Embargo, layer 1: landing.
--
-- The thesis of this project is that the registry publishes nothing about a
-- result while it is under review, and everything about it the moment review
-- ends. What we can see therefore depends on when we looked, and a store that
-- forgets when it looked cannot support a single claim the project makes.
--
-- So: raw payloads, exactly as received, with the time of receipt. A record
-- that changes is a new row. There is deliberately no update path.

BEGIN;

-- Coverage is evidence. A gap in collection must never read as a period in
-- which nothing was posted.
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id           bigserial   PRIMARY KEY,
    job              text        NOT NULL,          -- 'daily' | 'backfill' | 'history' | 'probe'
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    status           text        NOT NULL DEFAULT 'running',   -- running|ok|failed
    -- The registry's own statement of its freshness at the moment we called.
    -- A source that stops refreshing while still answering 200 is the failure
    -- that looks like success, and this column is how it gets caught.
    data_timestamp   timestamptz,
    api_version      text,
    http_calls       integer     NOT NULL DEFAULT 0,
    rows_appended    integer     NOT NULL DEFAULT 0,
    detail           jsonb       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ingest_runs_job_started ON ingest_runs (job, started_at DESC);

-- One row per (record, distinct content). Insert-if-changed: re-reading an
-- unchanged record costs nothing and adds nothing, but the FIRST time we see a
-- given state, that observation is kept forever with the date we saw it.
CREATE TABLE IF NOT EXISTS landing_study (
    nct_id           text        NOT NULL,
    content_sha256   bytea       NOT NULL,
    captured_at      timestamptz NOT NULL DEFAULT now(),
    ingest_run_id    bigint      NOT NULL REFERENCES ingest_runs(run_id),
    payload          jsonb       NOT NULL,

    PRIMARY KEY (nct_id, content_sha256)
);

CREATE INDEX IF NOT EXISTS landing_study_captured ON landing_study (captured_at);

-- A record revision, as reported by the history route. A version, once written,
-- describes a fact about the past and can never legitimately change: the
-- primary key is the guarantee, not a convention.
CREATE TABLE IF NOT EXISTS record_versions (
    nct_id           text        NOT NULL,
    version          integer     NOT NULL,
    version_date     date        NOT NULL,
    status           text,
    module_labels    text[]      NOT NULL DEFAULT '{}',
    -- True when this revision touched a results section. This is what makes the
    -- wait visible after the fact: a trial that posted in 2026 carrying results
    -- revisions dated 2024 spent those two years in a queue nobody could see.
    touched_results  boolean     NOT NULL DEFAULT false,
    captured_at      timestamptz NOT NULL DEFAULT now(),
    ingest_run_id    bigint      NOT NULL REFERENCES ingest_runs(run_id),

    PRIMARY KEY (nct_id, version),
    CONSTRAINT version_non_negative CHECK (version >= 0)
);

CREATE INDEX IF NOT EXISTS record_versions_date ON record_versions (version_date);
CREATE INDEX IF NOT EXISTS record_versions_results ON record_versions (nct_id) WHERE touched_results;

-- The point-in-time primitive, cached on first sight.
--
-- The history route is undocumented. It may be withdrawn or rate-limited
-- without notice, and every version already stored is one we never have to ask
-- for again. This table is the project surviving its own source.
CREATE TABLE IF NOT EXISTS version_payloads (
    nct_id           text        NOT NULL,
    version          integer     NOT NULL,
    captured_at      timestamptz NOT NULL DEFAULT now(),
    ingest_run_id    bigint      NOT NULL REFERENCES ingest_runs(run_id),
    payload          jsonb       NOT NULL,

    PRIMARY KEY (nct_id, version)
);

COMMIT;
