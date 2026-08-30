# Embargo — M3 Summary: Gate 2, the Census

**Milestone:** M3
**Date:** 2026-08-30
**Status:** Complete. **Gate 2 passes: 0 of 18 years disagree.**

| | |
|---|---|
| Repository | https://github.com/Muhammad-Haris-3/Embargo |
| Command | `python -m embargo.run_gates` |
| Verdict | recorded in `gate_results` |

---

## 1. Exit criterion

> Census reconciliation. Gate 2 runs.

Met.

```
[PASS] capture_faithful  0/200 failed
[PASS] census_agrees     0/18 failed

2 of 3 gates implemented; 2 run; 2 passed
The primary outcome may not be computed until all three pass.
```

That last line prints on every invocation. A runner that said "all gates
passed" would be true of the gates that exist and false about the project.

---

## 2. What Gate 2 checks, and why a total was not enough

For every year from 2008 to 2025: the number of trials whose results were
**first posted** in that year, counted in our warehouse, must equal the
registry's own `countTotal` for the same filter. **Exactly.** A count is not a
measurement and has no tolerance — if the registry says 6,521 trials posted in
2019 and we hold 6,520, we are missing one, and no threshold makes that
acceptable.

M1 noted that the backfill total matched the registry's 79,892 on the nose, and
said explicitly that this was encouraging and was *not* the gate. That caution
was the right one to keep: a total can match while the years inside it do not.
Two trials misattributed between 2014 and 2015 leave the total untouched and
the census broken.

Eighteen separate counts, eighteen agreements.

| Year | Trials posting results | | Year | Trials posting results |
|---:|---:|---|---:|---:|
| 2008 | 41 | | 2017 | 5,828 |
| 2009 | 1,099 | | 2018 | 4,660 |
| 2010 | 1,618 | | 2019 | 6,521 |
| 2011 | 2,203 | | 2020 | 6,043 |
| 2012 | 2,803 | | 2021 | 5,818 |
| 2013 | 3,091 | | 2022 | 4,023 |
| 2014 | 4,827 | | 2023 | 5,063 |
| 2015 | 3,803 | | 2024 | 6,829 |
| 2016 | 4,185 | | 2025 | 7,292 |

75,747 across the census window. The remainder of the 79,892 sits in 2026,
which the census deliberately excludes.

## 3. Three decisions inside the gate

**The current year is excluded, by preregistration.** 2026 is still
accumulating postings. Comparing a live count against a snapshot taken this
morning would fail for a reason that has nothing to do with whether our capture
is complete, and a gate that fails for reasons unrelated to what it tests is a
gate people learn to re-run.

**Trials are counted, not rows.** The warehouse is append-only, so a trial
recaptured after its record changed has more than one landing row. Counting
rows would inflate every year in which anything was recaptured. The census
counts the latest payload per trial.

**Over-counting fails too.** A gate that only checked for shortfalls would pass
while the warehouse invented evidence. `tests/test_gates.py` drives both
directions against a fake registry.

## 4. The gates are made to fail, offline

Gate 1 and Gate 2 have now only ever passed against live data, which proves
nothing about whether they *can* fail. `tests/test_gates.py` runs Gate 2
against a fake registry and a fake warehouse and asserts it fails on:

- a single missing trial in one year;
- one trial too many;
- a year we hold nothing for;

and that every year in the range is asked about, so a silently truncated loop
cannot pass by not looking.

## 5. Where the three gates stand

| Gate | Status | Result |
|---|---|---|
| 1 — capture is faithful | implemented, run | **PASS**, 0/200 |
| 2 — the census agrees | implemented, run | **PASS**, 0/18 |
| 3 — the estimator recovers a known queue | M4 | not yet written |

Gates 1 and 2 are both claims about plumbing: that the store holds what the
source served, and that it holds all of it. They were worth doing first
precisely because they are the least interesting things that could have been
wrong — and if either had failed, no amount of good estimation would have
mattered.

**Gate 3 is the one the project exists to pass, and it is the one that can
genuinely fail on its merits.**

## 6. Next

**M4: the estimator.** Right-censored survival on the wait, `Qhat(D)` committed
to the append-only register before it can be marked, `Qstar(D)` computed as the
realised lower bound, and Gate 3 comparing them at every mature date on the
preregistered freeze grid.

If Gate 3 fails, `PREREGISTRATION.md` requires the failure to be published and
**no current queue estimate published at all**. That instruction was written
before any estimator existed and it binds.
