-- Embargo, layer 3: append-only, enforced by grant rather than by convention.
--
-- Run as owner, after the tables exist. `embargo.migrate` runs it last and it
-- is idempotent.
--
-- The collector and the estimator both run as embargo_writer, which holds
-- INSERT and SELECT and nothing else. It physically cannot restate an
-- observation or withdraw an estimate it does not like. The API runs as
-- embargo_reader, which holds SELECT and nothing else.
--
-- tests/test_append_only.py connects AS embargo_writer and asserts that UPDATE
-- and DELETE both raise InsufficientPrivilege. A passing suite that never
-- attempts the forbidden write proves nothing at all.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'embargo_writer') THEN
        CREATE ROLE embargo_writer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'embargo_reader') THEN
        CREATE ROLE embargo_reader NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO embargo_writer, embargo_reader;

-- Writer: append and read. Never amend.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM embargo_writer;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO embargo_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM embargo_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO embargo_writer;

-- The one exception, and it is deliberate. A run log entry has to be closed
-- when the run finishes, which means the runs table alone permits UPDATE.
-- Nothing that constitutes evidence lives in it: it records that we looked, and
-- how it went, not what we found.
GRANT UPDATE ON ingest_runs TO embargo_writer;

-- Reader: nothing but SELECT, on everything.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM embargo_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO embargo_reader;

-- Same grants for anything created later, so a new table does not silently
-- arrive writable.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT ON TABLES TO embargo_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO embargo_reader;
