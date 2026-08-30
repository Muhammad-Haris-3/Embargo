"""M0 source characterisation.

Measured facts about the source, written to artifacts/source_facts.json.

Downfall established that the useful first milestone is not a pipeline, it is a
list of things about the feed that turned out to be true and that changed the
design. This is that list, and it runs against the live API with no database.

Six checks, each of which can fail and say so:

  freshness       what the registry says about its own currency
  invisibility    whether a result under review can be found at all
  disclosure      whether a posted record reveals the versions it submitted
                  during the wait -- the mechanism the entire validation rests
                  on, and the one listed under falsification
  waits           the shape of the wait distribution, on a knowingly biased
                  sample, labelled as such
  partial_dates   how often the dates the project turns on are month-precision
  anomalies       how often a result posts before it was submitted

Usage:
    python -m embargo.probe --sample 120
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from .clock import today_utc
from .config import ROOT, settings
from .ctgov import CtGov, parse_date, status_dates, wait_days
from .http import Http

ARTIFACT = ROOT / "artifacts" / "source_facts.json"

ANY_DATE = "RANGE[1900-01-01,MAX]"


def check_freshness(source: CtGov) -> dict[str, Any]:
    meta = source.data_timestamp()
    stamp = meta.get("dataTimestamp")
    age_hours = None
    if stamp:
        try:
            age_hours = round(
                (
                    dt.datetime.now(dt.UTC)
                    - dt.datetime.fromisoformat(stamp).replace(tzinfo=dt.UTC)
                ).total_seconds()
                / 3600.0,
                2,
            )
        except ValueError:
            pass
    return {
        "api_version": meta.get("apiVersion"),
        "data_timestamp": stamp,
        "age_hours_at_probe": age_hours,
        "note": "Observed to advance once a day around 09:00 UTC. Recorded on "
        "every run so that a frozen mirror answering 200 is detectable.",
    }


def check_invisibility(source: CtGov, sample: int) -> dict[str, Any]:
    """Can a result under review be found in the registry at all?

    Two independent ways of asking. If either says yes, the project premise is
    wrong and the estimator is unnecessary -- which would be excellent news and
    is written up as such.
    """
    counts = {
        "submit": source.count(query_term=f"AREA[ResultsFirstSubmitDate]{ANY_DATE}"),
        "qc": source.count(query_term=f"AREA[ResultsFirstSubmitQCDate]{ANY_DATE}"),
        "post": source.count(query_term=f"AREA[ResultsFirstPostDate]{ANY_DATE}"),
    }

    # Completed trials, primary completion long enough ago that some should have
    # submitted, none of which shows posted results. If the live record exposed
    # a pending submission, it would be here.
    term = (
        "AREA[PrimaryCompletionDate]RANGE[2024-01-01,2025-03-31]"
        f" AND NOT AREA[ResultsFirstPostDate]{ANY_DATE}"
    )
    cohort_size = source.count(query_term=term, **{"filter.overallStatus": "COMPLETED"})

    pending = 0
    checked = 0
    for study in source.search(
        query_term=term,
        page_size=min(sample, 1000),
        max_pages=1,
        **{"filter.overallStatus": "COMPLETED"},
    ):
        if checked >= sample:
            break
        checked += 1
        dates = status_dates(study)
        if dates["results_first_submit"] and not dates["results_first_post"]:
            pending += 1

    return {
        "counts_by_date_field": counts,
        "counts_are_identical": len(set(counts.values())) == 1,
        "unposted_cohort_size": cohort_size,
        "unposted_records_checked": checked,
        "unposted_records_exposing_a_submit_date": pending,
        "queue_is_invisible": len(set(counts.values())) == 1 and pending == 0,
        "note": "Identical counts mean the search index admits a record only "
        "once it has posted. Zero pending records among those checked means the "
        "live record does not expose a submission under review either.",
    }


def check_disclosure(source: CtGov, sample: int) -> dict[str, Any]:
    """Does a posted record reveal the versions submitted during its wait?

    This is the mechanism every later validation depends on. If a posted record
    does not carry results-touching versions dated before its post date, then
    the wait is not recoverable after the fact, Gate 3 cannot be marked, and
    PREREGISTRATION.md says so under falsification.
    """
    recent = today_utc() - dt.timedelta(days=120)
    disclosed = 0
    checked = 0
    no_history = 0
    examples: list[dict[str, Any]] = []

    for study in source.search(
        query_term=f"AREA[ResultsFirstPostDate]RANGE[{recent.isoformat()},MAX]",
        page_size=min(sample, 1000),
        max_pages=1,
    ):
        if checked >= sample:
            break
        dates = status_dates(study)
        nct_id, submit, post = (
            dates["nct_id"],
            dates["results_first_submit"],
            dates["results_first_post"],
        )
        if not (nct_id and submit and post):
            continue
        checked += 1
        try:
            versions = source.history(nct_id)
        except Exception:  # noqa: BLE001
            no_history += 1
            continue
        during = [v for v in versions if v.touched_results and submit <= v.version_date < post]
        if during:
            disclosed += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "nct_id": nct_id,
                        "submitted": submit.isoformat(),
                        "posted": post.isoformat(),
                        "wait_days": (post - submit).days,
                        "results_versions_during_wait": len(during),
                    }
                )

    rate = round(disclosed / checked, 4) if checked else None
    return {
        "records_checked": checked,
        "records_disclosing_the_wait": disclosed,
        "disclosure_rate": rate,
        "history_unavailable": no_history,
        "examples": examples,
        "note": "A record disclosing the wait carries results-module revisions "
        "dated between its submission and its posting. Gate 3 is only markable "
        "where this holds.",
    }


def check_waits(source: CtGov, sample: int) -> dict[str, Any]:
    """The shape of the wait, on a knowingly biased sample.

    Conditioning on records that posted since 2024 over-selects long waits: a
    trial submitted in 2010 and posted in 2025 is in, one submitted in 2010 and
    posted in 2011 is out. These numbers are a probe, not a finding, and M1
    recomputes them by submission cohort. The bias is stated in the artifact so
    that the number cannot later be quoted without it.
    """
    waits: list[int] = []
    negative = 0
    for study in source.search(
        query_term="AREA[ResultsFirstPostDate]RANGE[2024-01-01,MAX]",
        page_size=min(sample, 1000),
        max_pages=1,
        **{"filter.overallStatus": "COMPLETED"},
    ):
        if len(waits) + negative >= sample:
            break
        w = wait_days(status_dates(study))
        if w is None:
            continue
        if w < 0:
            negative += 1
            continue
        waits.append(w)

    if not waits:
        return {"n": 0, "note": "no waits computed"}

    waits.sort()

    def pct(f: float) -> int:
        return waits[min(len(waits) - 1, int(len(waits) * f))]

    return {
        "n": len(waits),
        "median_days": statistics.median(waits),
        "p75_days": pct(0.75),
        "p90_days": pct(0.90),
        "p99_days": pct(0.99),
        "max_days": waits[-1],
        "share_over_180d": round(sum(w > 180 for w in waits) / len(waits), 4),
        "share_over_365d": round(sum(w > 365 for w in waits) / len(waits), 4),
        "negative_waits": negative,
        "SELECTION_BIAS": "Conditions on records posted since 2024, which "
        "over-selects long waits. Provisional until M1 recomputes by submission "
        "cohort. Not a finding.",
    }


def check_partial_dates(source: CtGov, sample: int) -> dict[str, Any]:
    """How often are the dates the project turns on month-precision?"""
    seen = partial_submit = partial_post = 0
    for study in source.search(
        query_term="AREA[ResultsFirstPostDate]RANGE[2020-01-01,MAX]",
        page_size=min(sample, 1000),
        max_pages=1,
    ):
        if seen >= sample:
            break
        seen += 1
        status = (study.get("protocolSection") or {}).get("statusModule") or {}
        _, sp = parse_date(status.get("resultsFirstSubmitDate"))
        _, pp = parse_date((status.get("resultsFirstPostDateStruct") or {}).get("date"))
        partial_submit += sp
        partial_post += pp

    return {
        "records_checked": seen,
        "partial_submit_dates": partial_submit,
        "partial_post_dates": partial_post,
        "note": "PREREGISTRATION.md resolves a month-precision date to the "
        "first of that month and requires derived values to be flagged.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embargo M0 source probe")
    parser.add_argument("--sample", type=int, default=120)
    parser.add_argument("--out", type=Path, default=ARTIFACT)
    parser.add_argument("--skip", nargs="*", default=[], help="check names to skip (slow ones)")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    cfg = settings()
    facts: dict[str, Any] = {
        "probed_at": dt.datetime.now(dt.UTC).isoformat(),
        "sample_size": args.sample,
        "user_agent": cfg.user_agent,
    }

    with Http(
        user_agent=cfg.user_agent,
        min_interval_s=cfg.min_interval_s,
        max_retries=cfg.max_retries,
    ) as http:
        source = CtGov(http)
        checks = {
            "freshness": lambda: check_freshness(source),
            "invisibility": lambda: check_invisibility(source, args.sample),
            "disclosure": lambda: check_disclosure(source, min(args.sample, 40)),
            "waits": lambda: check_waits(source, max(args.sample, 500)),
            "partial_dates": lambda: check_partial_dates(source, args.sample),
        }
        for name, fn in checks.items():
            if name in args.skip:
                facts[name] = {"skipped": True}
                continue
            try:
                facts[name] = fn()
            except Exception as exc:  # noqa: BLE001
                facts[name] = {"failed": repr(exc)}
        facts["http_calls"] = http.calls

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(facts, indent=2, default=str), encoding="utf-8")
    print(json.dumps(facts, indent=2, default=str))
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
