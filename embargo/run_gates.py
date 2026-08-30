"""Run the preregistered gates and return the verdict as an exit status.

A gate failure must fail the build. `PREREGISTRATION.md` requires all gates to
pass before the primary outcome is computed at all, and a pipeline that reports
a failure with a zero exit code is a pipeline whose failures are advisory.

Usage:
    python -m embargo.run_gates
    python -m embargo.run_gates --gate 1
"""

from __future__ import annotations

import argparse
import sys

from .config import settings
from .ctgov import CtGov
from .db import connect
from .gates import gate1_capture_is_faithful, gate2_census_agrees
from .http import Http
from .runlog import run as run_log

# Gate 3 arrives at M4. Until then the runner says so on every invocation,
# because a green line reading 'all gates passed' would be true of the gates
# that exist and false about the project.
TOTAL = 3
IMPLEMENTED = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered gates")
    parser.add_argument("--gate", type=int, choices=(1, 2), default=None, help="run one gate")
    parser.add_argument("--size", type=int, default=None, help="override the sample size")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    cfg = settings()
    results = []
    with Http(
        user_agent=cfg.user_agent,
        min_interval_s=cfg.min_interval_s,
        max_retries=cfg.max_retries,
    ) as http:
        source = CtGov(http)
        with connect() as conn, run_log(conn, "gates", source=source) as state:
            if args.gate in (None, 1):
                kwargs = {"size": args.size} if args.size else {}
                result = gate1_capture_is_faithful(conn, source, state.run_id, **kwargs)
                result.record(conn)
                results.append(result)
            if args.gate in (None, 2):
                result = gate2_census_agrees(conn, source)
                result.record(conn)
                results.append(result)
            state.http_calls = http.calls
            state.note(gates={r.gate: r.passed for r in results})

    for result in results:
        print(result)
        for failure in result.detail.get("failures", []):
            print(f"    {failure}")

    # Reporting "all gates pass" while a gate is unimplemented, or was skipped
    # by --gate, would be the exact claim the preregistration exists to prevent.
    # So the line distinguishes what exists from what ran from what passed.
    print(
        f"\n{IMPLEMENTED} of {TOTAL} gates implemented; "
        f"{len(results)} run; {sum(r.passed for r in results)} passed"
    )
    if len(results) < TOTAL:
        print("The primary outcome may not be computed until all three pass.")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
