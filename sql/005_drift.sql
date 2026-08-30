-- Embargo, layer 5: the deadline-drift study.
--
-- This file is where risk R-9 gets answered.
--
-- The study needs the primary completion date at every revision of a record.
-- The obvious way to hold that is `version_payloads`, which keeps whole
-- records: at roughly 17 revisions per trial across 79,892 trials, that is
-- ~1.35M full records and several hundred megabytes against a 500 MB free
-- tier, for four dates per row.
--
-- So `version_status` stores the projection instead: the fields the study
-- reads, and nothing else. `version_payloads` keeps its place for Gate 1,
-- where the point is precisely that the whole record round-trips faithfully.
--
-- The projection is lossy on purpose, and that is a real cost: a question this
-- table cannot answer requires re-fetching from an undocumented endpoint that
-- may by then be gone. The trade is made deliberately, and named here so a
-- later reader knows it was a decision rather than an oversight.

BEGIN;

CREATE TABLE IF NOT EXISTS version_status (
    nct_id             text        NOT NULL,
    version            integer     NOT NULL,
    version_date       date        NOT NULL,
    -- The date the deadline is derived from, and the one the sponsor controls.
    primary_completion date,
    -- ACTUAL or ESTIMATED. An estimate becoming an actual is an ordinary and
    -- expected movement; conflating it with a revised estimate would put
    -- routine record-keeping into a drift count.
    completion_type    text,
    start_date         date,
    overall_status     text,
    captured_at        timestamptz NOT NULL DEFAULT now(),
    ingest_run_id      bigint      NOT NULL REFERENCES ingest_runs(run_id),

    PRIMARY KEY (nct_id, version)
);

CREATE INDEX IF NOT EXISTS version_status_trial ON version_status (nct_id, version);

-- One row per detected forward edit. Append-only, stamped, and recomputed as a
-- new snapshot rather than refreshed in place.
CREATE TABLE IF NOT EXISTS drift_events (
    computed_at        timestamptz NOT NULL DEFAULT now(),
    nct_id             text        NOT NULL,
    from_version       integer     NOT NULL,
    to_version         integer     NOT NULL,
    edited_on          date        NOT NULL,
    from_date          date        NOT NULL,
    to_date            date        NOT NULL,
    moved_days         integer     NOT NULL,
    from_type          text,
    to_type            text,
    sponsor_class      text,

    PRIMARY KEY (computed_at, nct_id, to_version),
    -- Forward only. A date moving backwards shortens the deadline and is not
    -- what the study is about; recording it here would make the count mean
    -- something other than its name.
    CONSTRAINT moved_forward CHECK (moved_days > 0)
);

CREATE TABLE IF NOT EXISTS drift_summary (
    computed_at        timestamptz NOT NULL,
    sponsor_class      text        NOT NULL,
    trials_sampled     integer     NOT NULL,
    trials_with_drift  integer     NOT NULL,
    edits              integer     NOT NULL,
    median_moved_days  integer,
    max_moved_days     integer,
    sample_size        integer     NOT NULL,
    sample_seed        bigint      NOT NULL,
    -- False while any primary gate fails. PREREGISTRATION.md reports the
    -- secondary study only if the primary gates pass, so the flag travels with
    -- the row rather than living in whoever remembers the rule.
    reportable         boolean     NOT NULL,

    PRIMARY KEY (computed_at, sponsor_class)
);

COMMIT;
