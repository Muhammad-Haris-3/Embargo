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
from .gates import gate1_capture_is_faithful
from .http import Http
from .runlog import run as run_log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the preregistered gates")
    parser.add_argument("--gate", type=int, choices=(1,), default=None, help="run one gate")
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
            state.http_calls = http.calls
            state.note(gates={r.gate: r.passed for r in results})

    for result in results:
        print(result)
        for failure in result.detail.get("failures", []):
            print(f"    {failure}")

    # Gates 2 and 3 do not exist yet. Reporting "all gates pass" while two of
    # three are unimplemented would be the exact claim the preregistration
    # exists to prevent, so say how many ran.
    print(f"\n{len(results)} of 3 gates implemented; {sum(r.passed for r in results)} passed")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
