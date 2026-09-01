# Methods

Every convention this project applies, and every piece of exploratory work,
labelled as such.

`PREREGISTRATION.md` is what was promised in advance. This document is what was
actually done, including the decisions too small for a preregistration and the
analyses that were never preregistered at all. Anything here that is not in the
preregistration is **exploratory**, and is marked.

---

## 1. Conventions that decide boundary cases

Each of these could otherwise have been chosen after seeing which way it moved
a number.

| Convention | Value | Fixed in |
|---|---|---|
| A month-precision date resolves to the first of that month | `PARTIAL_DATE_TO_MONTH_START` | Preregistration |
| Values derived from a partial date are flagged, never silently pooled | `has_partial_date` | Preregistration |
| A negative wait is excluded and counted, never clamped to zero | `NEGATIVE_WAIT_IS_ANOMALY` | Preregistration |
| Arithmetic is whole days in UTC | `ARITHMETIC` | Preregistration |
| A cohort is mature measured from **31 December** of its year | `embargo/waits.py` | Methods (here) |
| The observable set on date `D` is trials with `post <= D` | `AsOf.observable` | Preregistration (H1) |
| A gate that has never run counts as **not passed** | `api/gating.py` | Methods (here) |

**Maturity is measured from the end of the cohort year, not its start.** A trial
submitted in December had the least time of any member of its cohort, and dating
maturity from January would declare a cohort resolved while part of it still
could not be. This is a convention, not a preregistered constant, and it is
recorded here because it changes which cohorts are quotable.

**A gate that has never run counts as not passed.** The alternative — counting
only the gates present in the table — would make an empty `gate_results` read as
"all zero gates pass", which is how a preregistration gets satisfied by having
run nothing.

**Clamping.** Negative waits are excluded rather than clamped because a clamp
moves the median in a known direction, by exactly as many rows as there are
broken records. Measured: 0 negative waits in the M0 probe of 500.

## 2. What "today" means

`embargo/clock.py` holds one definition, and it is UTC.

The registry advances its own data timestamp on a UTC day boundary. A collector
using the machine local date computes a different day — and therefore a
different lookback window — depending on where it runs. In CI that is UTC and
the bug is invisible; on a laptop west of Greenwich it is off by one for part of
every day. This was a real defect, caught by a linter and fixed, not a
hypothetical.

## 3. Sampling

Two samples, both seeded, both ordered in SQL before the draw.

| Sample | Size | Seed | Fixed in |
|---|---|---|---|
| Gate 1 record revisions | 200 | 20260830 | Preregistration |
| Deadline-drift trials | 150 | 20260830 | Amendment 2 |

**Ordering before drawing is not cosmetic.** A seeded draw over a
non-deterministic row order is not reproducible: it becomes a fresh sample on
every run while appearing to honour the seed. For the drift sample it would also
grow silently as the history backlog drains.

## 4. Estimation

The queue estimator is `embargo/estimator.py`. Two components:

**Lynden–Bell** for the wait distribution. The waits visible on a date are
right-truncated — a trial submitted at `s` can only show a wait of `w` if
`s + w <= D` — so long waits are systematically missing, and averaging what is
visible produces a distribution that is too fast. Lynden–Bell is the
non-parametric maximum likelihood estimator for exactly this case.

**Reverse-time inflation** for the queue. Each observed trial stands for
`1 / F(T)` submissions from its slice of the cohort, of which `1 - F(T)` are
still waiting.

Two implementation choices worth recording:

- **The reverse risk set is computed as a difference of two counts.** Because
  `wait <= available` always holds, `#{j : wait_j <= x <= available_j}` equals
  `#{wait_j <= x} - #{available_j < x}`, which is two binary searches instead of
  a scan. The direct implementation is quadratic and does not finish on 75,000
  observations.
- **A floor of 0.05 on `F(T)`**, below which observations are dropped. Without
  it, a trial submitted days before the vantage date stands for thousands of
  submissions on the strength of nothing. The floor biases `Qhat` **downward**
  and the share dropped is reported beside every estimate. Measured at all nine
  freeze dates: **0.0% dropped**, so on this data the floor does nothing.

**The load-bearing assumption** is that the wait distribution does not depend on
when a trial was submitted. It is stated in the module docstring, it was written
before Gate 3 ran, and Gate 3 is what proved it wrong.

## 5. Exploratory work — not preregistered

Everything in this section is exploratory. None of it appears in
`DECISION_MEMO.md` and none of it is a finding.

**The M0 probe figures.** Median wait 104.5 days, p90 686, 21.0% over a year,
n = 500. Conditioned on records posted since 2024, which over-selects long
waits. Superseded by M1 and retained only because M0 predicted the direction of
its own error. Labelled `SELECTION_BIAS` in `artifacts/source_facts.json`.

**Immature cohort statistics.** Every cohort from 2017 onward is published on
the site and marked `censored`. Their medians are lower bounds on the wait for
those years, not estimates of it. They are shown because hiding them would hide
the shape of the censoring, which is what the project is about. They are not
quotable and the data says so on every row.

**The 2020–2021 dip.** The realised queue falls sharply at those two freeze
dates (2,192 and 2,168 against 3,344 the year before) and those are exactly
where the estimator overshoots by more than 80%. That pattern is what points at
non-stationarity as the cause of the Gate 3 failure. **No explanation of the dip
itself is offered**, and none should be read into it.

**Cohort medians ranging 44 to 174 days.** M1 declined to claim a trend and M4
did not compute one. Saying anything about direction requires handling the
censoring properly, which is what failed.

## 6. Diagnoses that were wrong

Recorded because a methods document listing only the diagnoses that survived is
a worse document.

**The Gate 3 failure was predicted to be the floor.** The floor discards the
newest submissions, biases downward, and six of nine dates were undercounts —
the fit was good. The share excluded is **0.0% at every date**. The floor was
doing nothing at all, and the real cause is the stationarity assumption.

**The history backlog was called the critical path for M2.** It is not. Gate 1
needs 200 revisions, the M4 estimator needs dates already in `landing_study`,
and only M7 needs revisions in bulk. Checking before building is what caught it.

## 7. What is deliberately not built

**A time-varying wait distribution.** It is the obvious repair for Gate 3 and it
is probably correct. It is also a rule that would be chosen after seeing which
dates it fixes. If built it goes in as a marked post-hoc amendment, reported as
weaker evidence than anything fixed in advance, with Gate 3 keeping its current
definition and continuing to fail.

**A narrowed reading of "the primary gates".** Excluding Gate 3 from the
secondary study's condition is defensible on the merits and became attractive
only on discovering that the broad reading blocks the drift result. See
`Embargo_M7_Summary.md` §2.

Explaining a failure is not passing one.
