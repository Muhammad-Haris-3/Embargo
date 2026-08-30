"""Qhat and Qstar: the estimate, and the answer that arrived later.

Two numbers for the same date, computed from different vantage points, and the
distance between them is the only thing this project asks to be believed about.

`Qhat(D)` uses **only what was observable on D** -- trials that had posted by
then. It is an estimate, committed to an append-only register before it can be
marked.

`Qstar(D)` uses **today's record**, in which every trial that has since posted
has disclosed both of its dates. It is a **lower bound and never the truth**: a
trial submitted before D that has still not posted is invisible today exactly as
it was invisible then. The column is called `q_star_lower` so the qualification
travels with the number.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .clock import today_utc
from .estimator import Observation, QueueEstimate, estimate_queue
from .knowability import AsOf
from .preregistration import (
    FREEZE_GRID_START,
    FREEZE_GRID_STEP_MONTHS,
    MATURITY_DAYS,
    PRIMARY_FREEZE_DATE,
)

METHOD = "lynden-bell + reverse-time inflation"


def method_digest() -> bytes:
    """A digest of the estimator source.

    Two estimates carrying the same method digest came from the same code. This
    is what makes "we reproduced it" checkable rather than asserted.
    """
    source = (Path(__file__).parent / "estimator.py").read_bytes()
    return hashlib.sha256(source).digest()


def freeze_grid(until: dt.date | None = None) -> list[dt.date]:
    """The preregistered grid of freeze dates.

    Fixed in advance so that a date cannot be added because the estimator did
    well on it, nor dropped because it did badly.
    """
    until = until or PRIMARY_FREEZE_DATE
    dates = []
    year = FREEZE_GRID_START.year
    while True:
        candidate = FREEZE_GRID_START.replace(year=year)
        if candidate > until:
            break
        dates.append(candidate)
        year += FREEZE_GRID_STEP_MONTHS // 12
    return dates


def is_mature(freeze_date: dt.date, today: dt.date | None = None) -> bool:
    """Has enough time passed for this date's queue to have resolved?"""
    return ((today or today_utc()) - freeze_date).days >= MATURITY_DAYS


def observations_at(records: list[dict[str, Any]], freeze_date: dt.date) -> list[Observation]:
    """What a person standing on the freeze date could have measured.

    The knowability guard supplies the observable set, so the rule lives in one
    place rather than being re-derived here with a comparison that might drift.
    """
    as_of = AsOf(freeze_date)
    out = []
    for record in as_of.observable(records):
        submit = record.get("results_first_submit")
        post = record.get("results_first_post")
        if not submit or not post:
            continue
        wait = (post - submit).days
        available = (freeze_date - submit).days
        # A negative wait is a broken record, excluded and counted upstream.
        # available < wait would mean the record posted after the freeze date,
        # which observable() has already ruled out; the guard stays anyway.
        if wait < 0 or available < wait:
            continue
        out.append(Observation(wait=wait, available=available))
    return out


def q_star_lower(records: list[dict[str, Any]], freeze_date: dt.date) -> int:
    """The realised queue at a past date, from today's record. A lower bound."""
    count = 0
    for record in records:
        submit = record.get("results_first_submit")
        post = record.get("results_first_post")
        if submit and post and submit <= freeze_date < post:
            count += 1
    return count


def still_pending(records: list[dict[str, Any]], freeze_date: dt.date) -> int:
    """Trials submitted before the date that have never posted.

    Zero, always, and that is the point rather than a bug: a trial that has not
    posted has not disclosed its submission date, so it cannot be counted here
    however certainly it exists. This function exists to make the hole in
    `q_star_lower` explicit instead of leaving it to a comment.
    """
    return sum(
        1
        for r in records
        if r.get("results_first_submit")
        and not r.get("results_first_post")
        and r["results_first_submit"] <= freeze_date
    )


@dataclass(frozen=True)
class FreezePoint:
    freeze_date: dt.date
    estimate: QueueEstimate
    q_star: int
    mature: bool
    inputs_digest: bytes

    @property
    def relative_error(self) -> float | None:
        if self.q_star == 0:
            return None
        return (self.estimate.q_hat - self.q_star) / self.q_star

    @property
    def below_the_bound(self) -> bool:
        """Qhat under Qstar contradicts something already on the table."""
        return self.estimate.q_hat < self.q_star


def evaluate(
    records: list[dict[str, Any]], freeze_date: dt.date, *, floor: float = 0.05
) -> FreezePoint:
    observations = observations_at(records, freeze_date)
    digest = hashlib.sha256(
        json.dumps(sorted((o.wait, o.available) for o in observations)).encode()
    ).digest()
    return FreezePoint(
        freeze_date=freeze_date,
        estimate=estimate_queue(observations, floor=floor),
        q_star=q_star_lower(records, freeze_date),
        mature=is_mature(freeze_date),
        inputs_digest=digest,
    )


def commit(conn: Any, run_id: int, point: FreezePoint) -> None:
    """Write the estimate and the realised bound to the append-only register.

    The writer role holds INSERT and nothing else, so an estimate that turns out
    badly cannot be withdrawn. That is the entire reason the register exists.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO queue_estimates
                (freeze_date, method, method_sha256, q_hat, inputs_sha256,
                 ingest_run_id, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                point.freeze_date,
                METHOD,
                method_digest(),
                round(point.estimate.q_hat, 2),
                point.inputs_digest,
                run_id,
                json.dumps(
                    {
                        "n_observed": point.estimate.n_observed,
                        "n_usable": point.estimate.n_usable,
                        "n_below_floor": point.estimate.n_below_floor,
                        "excluded_share": round(point.estimate.excluded_share, 4),
                        "floor": point.estimate.floor,
                        "inflation_max": round(point.estimate.inflation_max, 2),
                        "mature": point.mature,
                    },
                    default=str,
                ),
            ),
        )
        cur.execute(
            """
            INSERT INTO queue_realised
                (freeze_date, q_star_lower, cohort_coverage, is_mature, ingest_run_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                point.freeze_date,
                point.q_star,
                # Coverage of the relevant cohort is not knowable -- unposted
                # trials cannot be counted. Recorded as the share of observed
                # trials that cleared the floor, which is what the estimate
                # actually rests on.
                round(1.0 - point.estimate.excluded_share, 4),
                point.mature,
                run_id,
            ),
        )
