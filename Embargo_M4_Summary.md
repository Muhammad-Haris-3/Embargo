# Embargo — M4 Summary: Gate 3 Failed

**Milestone:** M4
**Date:** 2026-08-30
**Status:** **Gate 3 FAILS. No queue estimate is published.**

| | |
|---|---|
| Repository | https://github.com/Muhammad-Haris-3/Embargo |
| Command | `python -m embargo.run_gates` |
| Verdict | `gate_results`, and every estimate is in `queue_estimates` including the ones that failed |

---

## 1. The result

```
[FAIL] estimator_recovers  6/9 failed

3 of 3 gates implemented; 1 run; 0 passed
The primary outcome may not be computed until all three pass.
```

`PREREGISTRATION.md` says what happens next, and it was written before any
estimator existed:

> If Gate 3 fails, the failure is published and **no current queue estimate is
> published at all.**

Both halves hold. This document is the failure. **No figure for the number of
results currently in the queue appears anywhere in this repository**, and none
will until an estimator passes.

## 2. What was built

An estimator for a quantity that cannot be observed. On date `D` we see every
trial that has posted and not one that is waiting, so:

    Qhat(D) = sum over observed trials of (1 - F(T_i)) / F(T_i)

where `T_i` is the time trial `i` had available to post in. Each observed trial
stands for `1/F(T_i)` submissions from its slice of the cohort, of which
`1 - F(T_i)` are still waiting.

`F` cannot be counted either — the waits visible on `D` are right-truncated,
because a trial submitted at `s` can only show a wait of `w` if `s + w <= D`.
`embargo/estimator.py` uses **Lynden–Bell**, the non-parametric maximum
likelihood estimator for right-truncated data, which is the reverse-time
analogue of Kaplan–Meier.

It is tested against simulated worlds where the queue is counted directly, and
recovers it within 15% at two different wait distributions. **That test says the
implementation computes the method. Gate 3 says the method does not describe the
registry**, and those are different claims.

## 3. The failure, in full

Nine freeze dates on the preregistered grid. Tolerance 10%.

| Freeze date | Qhat | Qstar (lower bound) | Error | Mature |
|---|---:|---:|---:|:--|
| 2016-06-30 | 1,932 | 2,563 | **−24.6%** | yes |
| 2017-06-30 | 2,685 | 3,349 | **−19.8%** | yes |
| 2018-06-30 | 2,107 | 4,155 | **−49.3%** | no |
| 2019-06-30 | 2,926 | 3,344 | **−12.5%** | no |
| 2020-06-30 | 4,165 | 2,192 | **+90.0%** | no |
| 2021-06-30 | 3,978 | 2,168 | **+83.5%** | no |
| 2022-06-30 | 2,906 | 2,551 | +13.9% | no |
| 2023-06-30 | 2,803 | 3,781 | **−25.9%** | no |
| 2024-06-30 | 2,814 | 3,960 | **−29.0%** | no |

Six of nine fail. Both mature dates fail. The errors reach 90%, against a
tolerance of 10%.

Note the direction of the mature failures: `Qhat` falls **below** `Qstar`, and
`Qstar` is a lower bound assembled from disclosures that have already happened.
The estimate contradicts something already on the table, which the
preregistration calls a failure at any date, mature or not.

## 4. The diagnosis, and a prediction that was wrong

**I expected the floor to be the cause, and it was not.**

`estimate_queue` drops observations whose `F(T)` falls below 0.05, because a
trial submitted days before the freeze date would otherwise stand for thousands
of submissions on the strength of nothing. That exclusion biases `Qhat`
downward, it was documented in the estimator before the gate ran, and the
undercounts at six dates looked exactly like its signature.

It is not the cause. **The share excluded is 0.0% at every one of the nine
dates.** No observation was dropped anywhere, and the floor is doing nothing.

The actual cause is the assumption the estimator names as load-bearing in its
own docstring, written before Gate 3 ran:

> the wait distribution does not depend on when a trial was submitted

The errors are not a consistent undercount — they run from −49% to +90%. A
method biased by a mechanical exclusion errs in one direction. A method whose
pooled `F` is applied to a period when the true `F` was different errs in
whichever direction that period departed from the average. The realised queue
falls sharply at 2020-06-30 and 2021-06-30 (2,192 and 2,168, against 3,344 the
year before), and those are precisely the dates where `Qhat` overshoots by more
than 80%.

M1 already had the evidence and did not connect it: the mature cohort medians
range from **44 days (2014) to 174 days (2008)**, and M1 explicitly declined to
claim a trend because handling the censoring properly was M4's job. It is now
M4's job, and the answer is that the variation is real and large enough to break
a stationary estimator.

## 5. What happens next, and what may not

A time-varying `F` — estimated from a window of cohorts near each freeze date
rather than pooled across all of them — is the obvious repair, and it is
probably correct.

**It is also a rule chosen after seeing which dates it would fix, which is
gate-shopping.** If it is built, it will be an amendment to
`PREREGISTRATION.md`, marked post-hoc, reported as weaker evidence than
anything fixed in advance, and Gate 3 in its current form will keep its
definition and keep failing. Explaining a failure is not passing one.

The precedent is deliberate. `Hindsight` faced the same choice at its Gate 2,
wrote Amendment 2 to add a post-hoc convention, marked it as such, and left the
original gate failing.

## 6. What is true regardless

Gate 3 failing does not retract anything earlier:

- **Gate 1 passes**, 0/200. The store holds what the source served.
- **Gate 2 passes**, 0/18. The store holds all of it.
- **M1's wait figures stand**: median 81 days, p90 499, 13.6% over a year,
  across 26,984 waits from mature cohorts. Those are measured, not estimated,
  and they do not depend on the estimator.
- **The queue is still invisible and still real.** `Qstar` shows thousands of
  trials in it at every date measured — 2,563 on 2016-06-30, 3,960 on
  2024-06-30 — and those are lower bounds. What has failed is our ability to
  estimate the number *as it stood at the time*, not the claim that there is
  one.

## 7. Every estimate is in the register, including these

Nine estimates were committed to `queue_estimates` **before** they were compared
against anything, each with a digest of the estimator source and of its exact
inputs. The writer role holds `INSERT` and nothing else, so the six that failed
cannot be withdrawn.

A register holding only the estimates that turned out well would answer a
different question than the one asked.
