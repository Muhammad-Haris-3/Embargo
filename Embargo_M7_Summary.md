# Embargo — M7 Summary: Deadline Drift, Built and Withheld

**Milestone:** M7
**Date:** 2026-08-30
**Status:** Built, run, and **withheld**. 101 events detected and not reported.

| | |
|---|---|
| Command | `python -m embargo.run_drift` |
| Output | `FINDING WITHHELD — blocked by: estimator_recovers` |
| Stored | `drift_events`, `drift_summary`, all flagged `reportable = false` |

---

## 1. Exit criterion

> Deadline drift: forward-edit detection over stored versions, by sponsor
> class, with diffs.

The detection is built, tested and run. **The finding is not reported**, and
that is the criterion being met rather than missed.

`PREREGISTRATION.md` scopes the secondary study in one line:

> Separately scoped, separately gated, and **reported only if the primary gates
> pass**.

Gate 3 fails. So the runner computes the result, writes it to the database, and
prints:

```
sampled 150 trials; 93 have a stored trajectory
collected 1443 version-status rows this run

FINDING WITHHELD
  blocked by: estimator_recovers
```

## 2. The reading that was available and not taken

"The primary gates" could be read as Gates 1 and 2 — the checks on capture and
census — with Gate 3 excluded on the grounds that it validates the queue
*estimator*, which the drift study does not use. On the merits that reading is
defensible. Drift is computed from stored record revisions and touches nothing
Gate 3 tests.

**It was not taken, because of when it became attractive.** The narrowing
occurred to nobody while the gates were being written. It occurred immediately
on discovering that the broader reading blocks the interesting result. A rule
reinterpreted at the moment it starts costing something is not a rule, and the
whole project is an argument that this distinction is the one that matters.

If the narrowing is right it can be made — as a dated amendment, marked
post-hoc, with this paragraph still on the page saying when the idea arrived.

## 3. What the detector counts, and mostly does not

The study asks: how often does a sponsor move the primary completion date
forward, after the study has started? The deadline is twelve months after that
date, so moving it moves the deadline, and a tracker reading the current
snapshot cannot see the edit at all.

**The exclusions are tested harder than the inclusions**, because the harm this
study could do is counting ordinary record-keeping as sponsors moving
deadlines. `is_drift` requires all four:

| | Excluded because |
|---|---|
| Both revisions state a date | Nothing to compare otherwise |
| The date moved **forward** | Backwards shortens the deadline; counting it makes the number mean something other than its name |
| **Not** an estimate becoming an actual | A trial finishing later than planned records that fact. That is the registry working, and it would otherwise dominate the count |
| The edit came **after the study start** | A date changed before enrolment is planning |

The third is the one that matters. Without it the result would be mostly
routine date-keeping wearing the name of a finding.

`PREREGISTRATION.md` also forbids the inference the numbers invite:

> Nothing in this project licenses the sentence "this sponsor moved a deadline
> to avoid reporting," and that sentence will not appear.

It does not appear here.

## 4. Amendment 2, and why sampling was preregistered

The study needs the completion date at **every revision** of a record. There is
no bulk endpoint: it is one request per revision, against 74,400 collected
revisions, at about 0.98s each — roughly twenty hours of polling somebody
else's undocumented endpoint.

Amendment 2 fixed the sample at **150 trials under seed 20260830**, before any
edit was counted. It also fixed two things that protect the result from its own
size: the rate is reported with its uncertainty, and no claim is made about any
individual sponsor.

The draw is ordered in SQL before sampling. Without that the sample would grow
silently as the history backlog drains, while appearing to honour the seed.

## 5. R-9, answered

M1 flagged storage as a risk: ~17 revisions per trial across 79,892 trials is
~1.35M full records against a 500 MB tier.

`sql/005_drift.sql` answers it. **`version_status` stores the four dates the
study reads, not the whole record.** Measured after the first sweep: 1,443
revisions stored, database 139 MB → **140 MB**. The same revisions as full
records would have been roughly 100 MB by themselves.

The projection is lossy on purpose, and the cost is real: a question this table
cannot answer needs a re-fetch from an endpoint that may by then be gone. The
trade is named in the SQL file so a later reader knows it was a decision.

## 6. State

| | |
|---|---|
| Sample | 150 trials, seed 20260830 |
| Trajectories stored | 93 of 150 |
| `version_status` | 1,443 revisions |
| `drift_events` | **101** |
| `drift_summary` | 5 sponsor classes, every row `reportable = false` |

The sweep is time-boxed and resumes where it stopped, so the remaining 57
trajectories arrive on later runs. The count above will grow; none of it
becomes reportable by growing.

## 7. Next

Nothing in M7 unblocks until Gate 3 passes or the preregistration is amended.
The estimator repair — a wait distribution that varies over time — is the one
change that would move both this study and the primary outcome, and it remains
deliberately unbuilt for the reason M4 gives.
