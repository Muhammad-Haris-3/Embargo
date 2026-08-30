"""The secondary study: forward edits to the primary completion date.

The reporting deadline for a covered trial is twelve months after its primary
completion date, and the sponsor controls that date. Moving it forward moves
the deadline. A tracker reading the current snapshot cannot see such an edit --
the record simply has a later date than it used to, with nothing to compare
against. The version history records it precisely, with the day it was made.

**What this module reports is that a date moved, and when.** It does not report
why, and `PREREGISTRATION.md` forbids the inference:

    Nothing in this project licenses the sentence "this sponsor moved a deadline
    to avoid reporting," and that sentence will not appear.

Dates move for ordinary reasons far more often than for interesting ones.
Enrolment runs long. A site closes late. Most importantly an *estimate* becomes
an *actual*, which is not drift at all but the record working correctly, and
`is_drift` excludes it explicitly rather than leaving it to be noticed.

**Nothing here may be published while a primary gate fails.** The
preregistration scopes the secondary study that way, Gate 3 fails, and
`reportable` carries the consequence on every summary row.
"""

from __future__ import annotations

import datetime as dt
import itertools
import random
from dataclasses import dataclass
from typing import Any

from .ctgov import CtGov, parse_date
from .preregistration import DRIFT_SAMPLE_SIZE, DRIFT_SEED

# The module whose changes carry the dates. A revision that did not touch it
# cannot have moved a completion date, so there is no reason to fetch it.
STATUS_MODULE_LABEL = "Study Status"


@dataclass(frozen=True)
class VersionStatus:
    """A record's dates as they stood at one revision."""

    nct_id: str
    version: int
    version_date: dt.date
    primary_completion: dt.date | None
    completion_type: str | None
    start_date: dt.date | None
    overall_status: str | None


@dataclass(frozen=True)
class DriftEvent:
    nct_id: str
    from_version: int
    to_version: int
    edited_on: dt.date
    from_date: dt.date
    to_date: dt.date
    from_type: str | None
    to_type: str | None

    @property
    def moved_days(self) -> int:
        return (self.to_date - self.from_date).days


def project(
    nct_id: str, version: int, version_date: dt.date, payload: dict[str, Any]
) -> VersionStatus:
    """Pull the four dates the study reads out of a full record revision."""
    record = payload.get("study", payload)
    status = (record.get("protocolSection") or {}).get("statusModule") or {}
    pc = status.get("primaryCompletionDateStruct") or {}
    completion, _ = parse_date(pc.get("date"))
    start, _ = parse_date((status.get("startDateStruct") or {}).get("date"))
    return VersionStatus(
        nct_id=nct_id,
        version=version,
        version_date=version_date,
        primary_completion=completion,
        completion_type=pc.get("type"),
        start_date=start,
        overall_status=status.get("overallStatus"),
    )


def is_drift(before: VersionStatus, after: VersionStatus) -> bool:
    """Does this pair of revisions constitute a forward edit worth counting?

    Four conditions, and the third is the one that matters most.

    1. Both revisions state a primary completion date.
    2. The date moved **forward**. Backwards shortens the deadline and is not
       what the study is about.
    3. The revision did not merely replace an **estimate with an actual**. A
       trial that finishes later than planned records that fact, and counting it
       as drift would fill the result with ordinary record-keeping. Only
       estimate-to-estimate and actual-to-actual movements count.
    4. The edit was made **after the study started**. A date changed before
       enrolment began is planning, not a deadline moving.
    """
    if before.primary_completion is None or after.primary_completion is None:
        return False
    if after.primary_completion <= before.primary_completion:
        return False
    if before.completion_type == "ESTIMATED" and after.completion_type == "ACTUAL":
        return False
    start = before.start_date or after.start_date
    # An absent start date is not disqualifying: treating it as "before the
    # study started" would silently drop every record that omits one.
    return start is None or after.version_date >= start


def detect(trajectory: list[VersionStatus]) -> list[DriftEvent]:
    """Forward edits across a record's revisions, in order.

    Compares consecutive revisions that state a date, skipping over any that do
    not: a revision that dropped the field and one that restored it should not
    read as two edits with a gap between them.
    """
    stated = [v for v in sorted(trajectory, key=lambda v: v.version) if v.primary_completion]
    events = []
    for before, after in itertools.pairwise(stated):
        if is_drift(before, after):
            events.append(
                DriftEvent(
                    nct_id=after.nct_id,
                    from_version=before.version,
                    to_version=after.version,
                    edited_on=after.version_date,
                    from_date=before.primary_completion,
                    to_date=after.primary_completion,
                    from_type=before.completion_type,
                    to_type=after.completion_type,
                )
            )
    return events


def sample_trials(conn: Any, size: int = DRIFT_SAMPLE_SIZE, seed: int = DRIFT_SEED) -> list[str]:
    """Trials to study, drawn once under the preregistered seed.

    Ordered in SQL before the draw. Without that the sample is a fresh one on
    every run while appearing to honour the seed -- and here it would also grow
    silently as the history backlog drains.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT nct_id FROM record_versions ORDER BY nct_id")
        population = [r[0] for r in cur.fetchall()]
    if not population:
        return []
    return random.Random(seed).sample(population, min(size, len(population)))


def versions_to_fetch(conn: Any, nct_id: str) -> list[tuple[int, dt.date]]:
    """Revisions that touched the status module and are not already stored."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rv.version, rv.version_date
              FROM record_versions rv
             WHERE rv.nct_id = %s
               AND %s = ANY(rv.module_labels)
               AND NOT EXISTS (
                   SELECT 1 FROM version_status vs
                    WHERE vs.nct_id = rv.nct_id AND vs.version = rv.version
               )
             ORDER BY rv.version
            """,
            (nct_id, STATUS_MODULE_LABEL),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def stored_trajectory(conn: Any, nct_id: str) -> list[VersionStatus]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT nct_id, version, version_date, primary_completion,
                   completion_type, start_date, overall_status
              FROM version_status
             WHERE nct_id = %s
             ORDER BY version
            """,
            (nct_id,),
        )
        return [VersionStatus(*row) for row in cur.fetchall()]


def collect_trial(conn: Any, run_id: int, source: CtGov, nct_id: str) -> int:
    """Fetch and store the status projection for one trial. Returns rows added."""
    added = 0
    for version, version_date in versions_to_fetch(conn, nct_id):
        payload = source.version(nct_id, version)
        vs = project(nct_id, version, version_date, payload)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO version_status
                    (nct_id, version, version_date, primary_completion,
                     completion_type, start_date, overall_status, ingest_run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (nct_id, version) DO NOTHING
                """,
                (
                    vs.nct_id,
                    vs.version,
                    vs.version_date,
                    vs.primary_completion,
                    vs.completion_type,
                    vs.start_date,
                    vs.overall_status,
                    run_id,
                ),
            )
            added += cur.rowcount
    return added


def sponsor_classes(conn: Any, nct_ids: list[str]) -> dict[str, str]:
    """Lead sponsor class per trial, from the latest landed payload."""
    if not nct_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (nct_id) nct_id,
                   payload->'protocolSection'->'sponsorCollaboratorsModule'
                          ->'leadSponsor'->>'class'
              FROM landing_study
             WHERE nct_id = ANY(%s)
             ORDER BY nct_id, captured_at DESC
            """,
            (nct_ids,),
        )
        return {r[0]: (r[1] or "UNKNOWN") for r in cur.fetchall()}
