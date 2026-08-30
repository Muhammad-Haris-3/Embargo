# Preregistration

**Committed before any queue was estimated, any wait was counted, and any
sponsor was named.** Every constant in this document appears in
`embargo/preregistration.py` and is asserted against this file by
`tests/test_preregistration.py`. Changing a number here without changing it
there fails the build, and vice versa.

Amendments are appended below the line marked *Amendments*, with a date and a
reason. Nothing above that line is ever edited.

---

## H0 — What is being claimed

**The claim is not that quality-control review is slow.** Review exists because
a results record nobody has checked is not usable evidence, and the delay it
causes may well be the price of the record being worth reading.

The claim is narrower, and it is about measurement:

1. Between the moment a trial's results **exist** and the moment anyone can
   **read** them there is a delay that nobody has published.
2. The set of results in that state on any given day is **not observable** from
   the public record. A trial under review is indistinguishable from a trial
   that has reported nothing at all.
3. That set can be **estimated**, and the estimate can be **marked** against a
   truth that arrives later on its own schedule.

If the delay turns out to be negligible, or the queue turns out to be small,
that is the finding and it will be published with the same prominence as any
other.

## H1 — Primary quantity

For a trial `t`:

- **`submit(t)`** — `resultsFirstSubmitDate`, the day the sponsor delivered
  results to the registry.
- **`post(t)`** — `resultsFirstPostDateStruct.date`, the day those results
  became publicly readable.
- **`wait(t)`** — `post(t) - submit(t)` in whole days.

**Primary outcome: the embargo queue `Q(D)`** — the number of trials for which
`submit(t) <= D < post(t)`, estimated for a date `D` using only what was
observable on `D`.

Secondary outcomes, each reported by submission-cohort year and never pooled
across cohorts of different maturity:

- median and 90th-percentile `wait`;
- the share of trials with `wait > 365` days;
- **queue composition** — the distribution of elapsed waiting time inside
  `Q(D)`, which is the quantity a reader actually cares about and is strictly
  harder than the count.

### Why the primary outcome has to be estimated rather than counted

`Q(D)` is not observable on day `D`. This was measured, not assumed:

| Check, run 2026-08-30 | Result |
|---|---|
| Registry records carrying a results **submit** date | 79,892 |
| Registry records carrying a results **QC** date | 79,892 |
| Registry records carrying a results **post** date | 79,892 |
| Live records sampled from completed trials with no posted results, carrying a submit date | **0 of 120** |

The three counts are equal because the search index admits a trial only once it
has posted. The submission date is disclosed **retroactively**, at the moment
the wait ends. While a result is in the queue the registry publishes nothing
about it; when it posts, the entire history appears at once, including every
revision made during the wait.

This is the structure of a station that records no demand while it is empty. The
observation is destroyed by the condition that makes it interesting.

## Fixed before the fact

| Constant | Value | Where |
|---|---|---|
| Primary freeze date `D0` | `2024-06-30` | `prereg.PRIMARY_FREEZE_DATE` |
| Secondary freeze grid, start | `2016-06-30` | `prereg.FREEZE_GRID_START` |
| Secondary freeze grid, step | `12` months | `prereg.FREEZE_GRID_STEP_MONTHS` |
| Cohort maturity horizon | `2555` days | `prereg.MATURITY_DAYS` |
| Queue estimate tolerance (Gate 3) | `0.10` relative | `prereg.QUEUE_TOL` |
| Census years (Gate 2) | `2008` .. `2025` | `prereg.CENSUS_START_YEAR`, `prereg.CENSUS_END_YEAR` |
| Gate 1 sample size | `200` | `prereg.GATE1_SAMPLE_SIZE` |
| Gate 1 seed | `20260830` | `prereg.GATE1_SEED` |
| Minimum cohort coverage to publish | `0.98` | `prereg.MIN_COHORT_COVERAGE` |
| Statutory reporting deadline | `12` months | `prereg.REPORTING_DEADLINE_MONTHS` |
| Drift is any forward edit of the primary completion date | `True` | `prereg.DRIFT_IS_FORWARD_EDIT` |
| Partial dates resolve to the first of the month | `True` | `prereg.PARTIAL_DATE_TO_MONTH_START` |
| Negative waits are excluded and counted | `True` | `prereg.NEGATIVE_WAIT_IS_ANOMALY` |
| Arithmetic | `integer-days-utc` | `prereg.ARITHMETIC` |
| Poll hour, UTC | `7` | `prereg.POLL_HOUR_UTC` |

Three of these decide boundary cases that are not hypothetical, and each is
fixed here because it could otherwise be chosen after seeing which way it moved
the headline:

**Partial dates.** The registry publishes some dates to month precision. A
month-precision date resolves to the first day of that month, and any quantity
derived from one is flagged in the output rather than silently mixed with a
day-precision quantity.

**Negative waits.** `post < submit` is arithmetically possible in the record and
means something went wrong upstream. Such rows are excluded from every wait
statistic and reported as a count. They are never clamped to zero, because a
clamp moves the median in a known direction.

**Cohort maturity.** A submission cohort is *mature* when `MATURITY_DAYS` have
elapsed since its submission date, at which point it is treated as effectively
complete for the purpose of Gate 3. 2555 days is seven years. It is set from the
shape of the wait distribution, not from convenience: an unweighted probe of
1,000 posted trials put the 99th percentile of `wait` at 2,075 days, and the
horizon must sit beyond that with room to spare. **That probe conditions on
trials that posted, which over-selects long waits, and its numbers are
provisional until M1 recomputes them by cohort.** If M1 finds the 99th
percentile beyond 2555 days, that is an amendment, recorded below, and not a
silent edit.

## Universe

Every registered study that has ever had a results submission, without
restriction by phase, sponsor class, intervention type, or country. Fixed in
full now so that a subgroup cannot be added later because it looked promising,
and cannot be dropped later because it did not.

The universe deliberately does **not** condition on whether a trial was legally
required to report. That determination is genuinely hard, is the reason existing
compliance trackers rely on a documented heuristic, and is **not needed for the
primary outcome**: the wait between submission and posting applies to every
submission regardless of what compelled it. It is needed only for the deadline
work below, which is scoped and gated separately.

## Validation before any finding is reported

Three gates. **None is a robustness check run afterwards; all must pass before
the primary outcome is computed at all**, and all are enforced by
`tests/test_validation_gates.py`.

**Gate 1 — the capture is faithful.** For a random sample of
`GATE1_SAMPLE_SIZE` `(nct_id, version)` pairs drawn under `GATE1_SEED`, the
record version reconstructed from our store must equal the record the API
returns for that version, field for field across the status module. This tests
our storage and our joins, not our arithmetic.

**Gate 2 — the census agrees.** For every year from `CENSUS_START_YEAR` to
`CENSUS_END_YEAR`, our warehouse's count of trials with results first posted in
that year must equal the registry's own `countTotal` for the same filter.
**Exactly.** A count is not a measurement and has no tolerance.

**Gate 3 — the estimator recovers a queue whose size is already known.**

This is the point of the design, and it is the gate the project exists to pass.

For each date `D` on the secondary freeze grid whose cohorts are mature:

1. Estimate `Qhat(D)` using **only records observable on `D`** — that is, trials
   that had already posted by `D`. Nothing submitted-but-pending may enter the
   estimate, because on `D` nothing submitted-but-pending was visible.
2. Compute `Qstar(D)`, the realised queue, from today's record: every trial with
   `submit(t) <= D < post(t)` is now plainly visible, because both dates are now
   disclosed.
3. `Qhat(D)` must fall within `QUEUE_TOL` of `Qstar(D)`.

**`Qstar(D)` is a lower bound, not the truth, and is reported as one.** A trial
submitted before `D` that has *still* not posted is invisible today exactly as
it was invisible on `D`. The bound tightens as postings arrive, and is tightest
for the oldest grid dates — which is why maturity decides which dates count.
`Qhat(D) < Qstar(D)` is therefore a failure at any `D`, mature or not: the
estimator has contradicted something already on the table.

If Gate 3 fails, the failure is published and **no current queue estimate is
published at all.**

## Stopping rule

The primary outcome is computed **once**, at `PRIMARY_FREEZE_DATE`, after all
three gates pass. It is not recomputed with a different maturity horizon, a
different estimator, or a different grid. If any of those are explored they
appear under *Exploratory* in `METHODS.md`, labelled as such, and never in
`DECISION_MEMO.md`.

The live queue figure shown by the application is a **running** quantity, not
the primary outcome, and is labelled as such wherever it appears.

## Secondary study — deadline drift

Separately scoped, separately gated, and reported only if the primary gates
pass.

The reporting deadline for a covered trial is `REPORTING_DEADLINE_MONTHS` after
its primary completion date, and **the sponsor controls the primary completion
date.** An edit that moves it forward moves the deadline. A tracker reading the
current snapshot cannot see such an edit; the version history records it
precisely, with the date it was made.

What will be reported is the **rate of forward edits to the primary completion
date made after the study start date**, by sponsor class, with the version dates
either side of each edit.

What will **not** be reported is intent. A date moves for many reasons, most of
them ordinary — enrolment ran long, a site closed late, the original date was an
estimate and the actual one arrived. The finding is that the record moved, and
when. Nothing in this project licenses the sentence "this sponsor moved a
deadline to avoid reporting," and that sentence will not appear.

## What would falsify the thesis

- A median `wait` at or near zero once cohorts are computed properly.
- `Qstar(D0)` small enough that the queue is not a meaningful category.
- Gate 1 failing on more than zero pairs.
- **The retrospective disclosure not holding** — that is, posted records whose
  history does not reveal the versions submitted during the wait. This is the
  mechanism the entire validation rests on. It has been confirmed on one trial
  and not yet on a sample, and M0 is where it is tested properly.

Any of these is a publishable result and will be published.

## What this project will not do

- **It will not claim the registry is failing.** Review is a service, the delay
  may be its cost, and this project measures the delay rather than judging it.
- **It will not name a sponsor as non-compliant.** Compliance is a legal
  determination this project does not make.
- **It will not infer intent from a date.**
- **It will not scrape the website.** Everything comes from the public API, at a
  polite rate, with a contact address in the user agent.

---

## Amendments

*None yet.*
