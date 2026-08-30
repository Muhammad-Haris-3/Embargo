# Embargo — M2 Summary: Reconstruction, the Guard, and Gate 1

**Milestone:** M2
**Date:** 2026-08-30
**Status:** Complete. **Gate 1 passes: 0 of 200.**

| | |
|---|---|
| Repository | https://github.com/Muhammad-Haris-3/Embargo |
| Command | `python -m embargo.run_gates` |
| Verdict | recorded in `gate_results`, not asserted in prose |

---

## 1. Exit criterion

> Point-in-time reconstruction and the knowability guard. Gate 1 runs.

Met. Gate 1 ran against the live registry over a seeded sample of 200
revisions and **passed with zero failures**. The verdict is a row in
`gate_results` with its seed and sample size recorded beside it.

```
[PASS] capture_faithful  0/200 failed

1 of 3 gates implemented; 1 passed
```

The second line is deliberate. Printing "all gates pass" while two of three are
unimplemented would be precisely the claim `PREREGISTRATION.md` exists to
prevent, so the runner says how many exist.

---

## 2. A correction to the M1 plan

M1 closed by naming the history backlog as the critical path for M2, on the
grounds that reconstruction needs stored revisions and 75,000 trials were
undrained at roughly 1,500 a day.

**That was wrong, and checking it before building was what caught it.**

| Consumer | What it actually needs | Bulk revisions required |
|---|---|---|
| Gate 1 | 200 sampled revisions | no |
| M4 estimator, Gate 3 | submit and post dates, already in `landing_study` | no |
| M7 deadline drift | primary completion dates across revisions | **yes** |

Reconstruction needs the *capability*, exercised on demand and cached on first
sight — not an archive assembled in advance. The backlog is the critical path
for **M7**, and M2 through M4 are not blocked on it. The store holds 200
revisions today, fetched because a gate asked for them.

This also settles risk **R-9** for now: there is no bulk version-payload
collection to size, so the storage projection that worried M1 does not apply at
this milestone. It returns at M7, and is decided then against a known cohort
rather than against the whole registry.

## 3. What was built

### 3.1 The knowability guard

`embargo/knowability.py`. `AsOf` wraps the date being reconstructed, and every
dated value entering a point-in-time computation passes through it. A value
dated later than the vantage point raises `NotKnowable` rather than returning
something plausible.

The rule that matters is `AsOf.observable`, which is the project's premise in
one place:

> A trial that had not posted by `D` was, on that day, indistinguishable from
> one that had submitted nothing — so it is not in the observable set, and
> neither is its submission date, however plainly both are visible now.

`tests/test_knowability.py` attacks it: a record posted the day after the
vantage point, a record never posted, a negative elapsed time. A guard nobody
tries to break is a guard nobody has tested.

### 3.2 Point-in-time reconstruction

`embargo/pit.py`. One rule:

> the current revision on date `D` is the latest revision dated on or before `D`

It does not interpolate — a record untouched between March 2015 and September
2016 looked, on 1 January 2016, exactly as it did in March 2015, and there is
no intermediate state to invent. It does not reach forward. Both are tested at
the day boundary, because being wrong by one day here would be invisible in
every downstream output.

Revisions are cached on first sight, so a date already reconstructed does not
depend on the undocumented history route still existing.

### 3.3 Gate 1

`embargo/gates.py`. For each of 200 `(nct_id, version)` pairs drawn under the
preregistered seed `20260830`: store the revision if absent, read our stored
copy back **out of the database**, and compare its status module field by field
against a fresh fetch from the API.

The round trip through `jsonb` is where a date becomes a string, a null becomes
an absent key, or ordering shifts — none of it visible until something computes
a wrong number downstream. Reading back from the database rather than comparing
the in-memory object is what makes the check mean anything.

Zero tolerance, and preregistered as such: this is an identity check, and one
disagreement means the store is not holding what it was given.

**The sample is ordered in SQL before it is drawn.** A seeded draw over a
non-deterministic row order is not reproducible, and would quietly become a
fresh sample on every run while appearing to honour the seed.

## 4. What M2 did not do

- **Gate 2 and Gate 3 do not exist.** M3 and M4.
- **No queue is estimated**, and none may be until all three gates pass.
- **No bulk reconstruction was performed.** 200 revisions are stored because a
  gate asked for them, and nothing else has asked.
- **Gate 1 passing says nothing about the finding.** It says the store holds
  what the source served. That is a claim about plumbing, and it was worth
  making first precisely because it is the least interesting thing that could
  have been wrong.

## 5. State

| | |
|---|---|
| `landing_study` | 79,892 rows / 79,892 trials |
| `record_versions` | 74,400 rows / 4,398 trials |
| `version_payloads` | 200 revisions / 183 trials |
| `gate_results` | 1 row: `capture_faithful`, passed, 0/200 |
| Database | 139 MB |

## 6. Next

**M3: Gate 2 — the census agrees.** Our per-year count of trials with results
first posted must equal the registry's own `countTotal`, exactly, for every year
2008–2025. The backfill already matched the registry's total of 79,892 on the
nose, which is encouraging and is not the gate: the gate is 18 separate yearly
counts, and a total can match while the years inside it do not.
