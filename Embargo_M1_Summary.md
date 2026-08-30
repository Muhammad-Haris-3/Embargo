# Embargo — M1 Summary: The Wait, By Cohort

**Milestone:** M1
**Date:** 2026-08-30
**Status:** Core deliverable complete. The M0 probe figure is retired.

| Surface | |
|---|---|
| Repository | https://github.com/Muhammad-Haris-3/Embargo |
| Warehouse | Neon, AWS `us-east-2`, PostgreSQL 18.6 |
| Artifact | [`artifacts/wait_cohorts.json`](artifacts/wait_cohorts.json) |
| Command | `python -m embargo.waits` |

---

## 1. Exit criterion

> Backfill complete. Wait distribution recomputed by submission cohort,
> replacing the biased probe figures. Coverage published.

Met. The backfill landed 79,892 of 79,892 records — every trial the registry
holds with posted results — and the wait is now computed from all of them
rather than from a sample of 500.

---

## 2. The headline, and what replaced what

M0 reported a median wait of about 100 days and said, in the artifact and in
the spec, that the number was provisional and biased. It was.

| | M0 probe | M1, horizon 2555d | **M1, horizon 3285d** |
|---|---|---|---|
| Cohorts | n/a | 2008–2018 | **2008–2016** |
| n | 500 | 38,052 | **26,984** |
| Median wait | 104.5 days | 91 days | **81 days** |
| p90 | 686 days | 543 days | **499 days** |
| Share over 365 days | 21.0% | 15.9% | **13.6%** |

**The bolded column is the figure of record.** It is computed from mature
submission cohorts only — 2008 through 2016 — and those are the only figures in
this project that may be quoted as the wait.

The middle column is shown because it was computed, under the horizon in force
at the time, before Amendment 1 raised it (§5). Deleting it would hide the
amendment rather than record it. Note the direction: raising the horizon made
the headline **smaller**, because the two cohorts it removed (2017 and 2018,
both with a median of 120 days) were among the slowest. The amendment was not
chosen for its effect on the number, and its effect on the number was not the
convenient one.

The direction of the correction is the one M0 predicted in advance. That
matters more than the size of it: the bias was named, written down, and then
measured, rather than discovered afterwards and explained.

## 3. Why the probe was wrong, and why cohorts are not simply right

Two biases, pointing opposite ways. Neither corrects the other, and the whole
of M1 is about keeping them apart.

**The probe selected on the outcome.** It took records posted since 2024. A
trial submitted in 2010 and posted in 2025 is in that sample; one submitted in
2010 and posted in 2011 is not. The longer a record waited, the likelier it was
to surface inside a recent window — so the sample over-represented long waits
and the median came out high.

**Cohorts remove that selection and expose a different one.** Grouping by year
of submission means a trial belongs to its cohort regardless of when it
emerged. But a cohort can only show the trials that *have* emerged. The ones
still in review are invisible — that is the premise of this entire project —
so a recent cohort displays only its fast members and its median is biased
**downward**.

The observable consequence is in the table below. The 2025 cohort shows a
median of 58 days and 1.7% over a year. That is not a year in which review got
faster. It is a year most of whose slow cases have not come back yet.

## 4. Every cohort, and which ones may be quoted

| Cohort | n | Median | p90 | >365d | Quotable |
|---:|---:|---:|---:|---:|:---|
| 2008 | 204 | 174 | 490 | 21.1% | yes |
| 2009 | 1,664 | 101 | 662 | 16.7% | yes |
| 2010 | 1,768 | 70 | 558 | 13.4% | yes |
| 2011 | 2,530 | 77 | 530 | 14.5% | yes |
| 2012 | 3,094 | 76 | 476 | 12.5% | yes |
| 2013 | 3,909 | 114 | 602 | 16.3% | yes |
| 2014 | 4,160 | 44 | 343 | 9.5% | yes |
| 2015 | 4,605 | 66 | 447 | 12.2% | yes |
| 2016 | 5,050 | 114 | 539 | 15.0% | yes |
| 2017 | 6,053 | 120 | 633 | 24.1% | **no — censored** |
| 2018 | 5,015 | 120 | 506 | 18.3% | **no — censored** |
| 2019 | 5,089 | 68 | 342 | 9.2% | **no — censored** |
| 2020 | 5,871 | 48 | 213 | 5.5% | **no — censored** |
| 2021 | 5,716 | 66 | 353 | 9.8% | **no — censored** |
| 2022 | 5,140 | 107 | 710 | 24.1% | **no — censored** |
| 2023 | 5,818 | 103 | 516 | 19.3% | **no — censored** |
| 2024 | 5,725 | 90 | 317 | 7.4% | **no — censored** |
| 2025 | 5,991 | 58 | 189 | 1.7% | **no — censored** |
| 2026 | 2,473 | 54 | 112 | 0.0% | **no — censored** |

Maturity is `MATURITY_DAYS` (3,285 days, per Amendment 1) measured from
**31 December of the cohort year**, not from its start. A trial submitted in December had the least
time of any member of its cohort, and dating maturity from the start of the
year would declare a cohort resolved while part of it still could not be.

`n` is a **lower bound in every row**, including the mature ones. It counts the
trials from that cohort which have posted. The ones still in review cannot be
seen or counted — the field `n_is_lower_bound` says so on every record in the
artifact, so the number cannot be lifted out of context.

## 5. The preregistered constant that did not survive contact

`PREREGISTRATION.md` fixed `MATURITY_DAYS` at 2,555 days on the strength of an
M0 probe that put the 99th percentile of the wait at 2,075 days, and committed
in advance:

> If M1 finds the 99th percentile beyond 2555 days, that is an amendment,
> recorded below, and not a silent edit.

**M1 found it beyond 2,555 days, and an amendment is therefore required.**

| Mature cohort | p99 | Exceeds the horizon by |
|---:|---:|---:|
| 2011 | 2,963 days | 408 days |
| 2012 | 2,750 days | 195 days |

The M0 probe underestimated the tail, for the reason M0 already recorded: it
was a single biased sample of 500 records, and its p99 was the least reliable
number in it.

The horizon exists so that a cohort called mature has essentially finished
resolving. Two mature cohorts have a 1-in-100 case still arriving after the
horizon has passed, so as written the definition does not do what it says.

**This is the preregistration costing something, which is the only moment its
existence is worth anything.** The clause was written when no such conflict
existed; the resolution is recorded as Amendment 1 in `PREREGISTRATION.md`,
marked post-hoc, and the headline figures in §2 are stated under the horizon in
force when they were computed.

## 6. What M1 did not do

- **No queue is estimated.** `Qhat` does not exist until M4, and only after
  three gates pass.
- **No cohort trend is claimed.** The mature medians move between 44 and 174
  days with no direction argued here. Saying anything about that requires
  handling the censoring properly, which is M4's estimator, not a table.
- **No sponsor appears.** Sponsor class is captured and unanalysed.
- **The immature cohorts are published anyway**, labelled, because publishing
  only the quotable half would hide the shape of the censoring — which is the
  thing this project is ultimately about.

## 7. Next

M2: point-in-time reconstruction and the knowability guard, then Gate 1. It
needs the record histories, and that backlog is draining at roughly 1,500
trials a day against 75,000 remaining. **That rate, not the analysis, is now
the critical path**, and the SRS response to it (R-9, storing the status module
rather than whole records) has to be decided before M2 rather than during it.
