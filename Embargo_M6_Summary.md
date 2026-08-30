# Embargo — M6 Summary: The Application

**Milestone:** M6
**Date:** 2026-08-30
**Status:** Complete. Deployed and verified live.

| | |
|---|---|
| Repository | https://github.com/Muhammad-Haris-3/Embargo |
| App | `web/`, Next.js 16 App Router, matching GridCast's structure |
| Run locally | `cd web && npm install && npm run dev` |

---

## 1. Exit criterion

> The application: live queue, calibration, recent postings, coverage.

Partly met, and the shortfall is the point rather than a gap. **There is no
live queue view, because there is no live queue figure.** Gate 3 fails, so the
primary outcome is withheld, and the front page leads with that.

---

## 2. The front page leads with the number that is not there

The largest element on the site reads:

> **RESULTS IN THE QUEUE RIGHT NOW**
> **Withheld**
> The primary outcome is withheld because estimator_recovers failing.
> PREREGISTRATION.md requires all three gates to pass before any queue estimate
> is published.

FR-32 requires refused and failed results to be published with the same
prominence as passing ones. Here the refusal is *more* prominent than anything
that passed, because a project whose headline is an absence should not bury the
absence beneath the figures that happened to work out.

The reason text is not written into the page. It comes from `/v1/queue/current`,
which computes it from the gate table on every request — so if Gate 3 starts
passing, the page stops saying it without anyone editing the page, and if a
different gate fails, the page names that one instead.

## 3. Four pages

| Page | What it shows |
|---|---|
| `/` | The withheld figure, what is known instead, and the three gate verdicts |
| `/cohorts` | The wait by submission cohort, censored rows greyed and marked |
| `/register` | Every committed estimate against the bound it was marked by |
| `/coverage` | Which days the collector ran, and which runs never closed |

Three decisions carried from the data into the interface:

**Censored rows are shown, not hidden.** An immature cohort's median is a lower
bound, and the greyed rows with `censored` pills are how the shape of the
censoring stays visible. Publishing only the quotable half would hide the thing
the project is about.

**Q\* is printed with a `≥`.** It is a lower bound and never the truth, and the
symbol travels with the number so it cannot be quoted without its
qualification.

**Failed estimates stay on the register.** All nine appear, six of them flagged,
because a register holding only the estimates that worked answers a different
question than the one asked.

## 4. What was verified, and how

This check was written before Node was available, when a build could not be
run at all, and it is kept because it catches something a build does not.

**The API contract.** A script compares every TypeScript type in `web/lib/api.ts`
against the live JSON from each endpoint, including nested element types. A
build cannot catch this: a field renamed in the API still typechecks against a
client that declares it, compiles cleanly, and renders `undefined` into a table
cell at runtime.

```
OK  /v1/status             type Status         missing_in_api=-
OK  /v1/gates              type Gates          missing_in_api=-
OK  /v1/waits/cohorts      type Cohorts        missing_in_api=-
OK  /v1/coverage           type Coverage       missing_in_api=-
OK  cohorts[0]             type Cohort         missing_in_api=-
OK  register points[0]     type RegisterPoint  missing_in_api=-
OK  coverage days[0]       type CoverageDay    missing_in_api=-
OK  /v1/queue/current(409) type Withheld       missing_in_api=-

CONTRACT OK
```

## 5. Built and verified

Node was installed and the app now builds. Everything in the previous draft of
this section — `npm install`, `tsc --noEmit`, `next build` — has run.

```
> tsc --noEmit                      (no output)
> next build
✓ Compiled successfully in 17.0s
✓ Generating static pages (6/6)

Route (app)      Revalidate  Expire
┌ ○ /                    5m      1y
├ ○ /cohorts             5m      1y
├ ○ /coverage            5m      1y
└ ○ /register            5m      1y
```

Then rebuilt with the API running against Neon, and the generated HTML
inspected rather than assumed. The pages carry real rows:

| Page | Rendered |
|---|---|
| `/` | "Withheld — the primary outcome is withheld because estimator_recovers failing", pulled live, and all three gate verdicts |
| `/cohorts` | 19 rows, `2008 / 204 / 174 d / 490 d / 21.1% / yes` through `2026 / 2,473 / 54 d / censored` |
| `/register` | 9 rows, `2016-06-30 / 1,932 / ≥ 2,563 / −24.6%` through `2024-06-30 / 2,814 / ≥ 3,960 / −28.9%` |
| `/coverage` | 79,892 trials and the run log |

Two things worth noting from the render.

**The withheld reason is not in the page source.** It arrived from
`/v1/queue/current`, so the site says what the gate table says, and will stop
saying it when the gate stops failing.

**The `≥` renders on every Q\* cell.** The bound travels with the number in the
markup, not only in the prose beside it.

## 6. Deployed

| | |
|---|---|
| Site | https://embargo-silk.vercel.app |
| API | https://embargo-api-kz73.onrender.com |

Verified against the deployed services rather than assumed: all seven API
endpoints answer, `/v1/queue/current` returns **409** naming the failing gate,
and the live pages carry 19 cohort rows, 9 register rows and 3 gate verdicts.

**The first Vercel build shipped four pages reading "the API may be waking
up".** A free Render container answers 502 from its router for the 30+ seconds
it takes to start, one fetch attempt failed, and because the pages are
prerendered that failure was baked into the HTML every visitor would see until
revalidation. The data and the code were both fine.

`get()` now retries four times with backoff, up to about 38 seconds — a slow
build being cheaper than a wrong one. A 4xx is deliberately not retried: it is
an answer rather than an outage, and retrying the 409 would turn the withheld
figure into a missing one.

## 7. Next

M7, deadline drift — the one milestone that needs the record-history backlog,
which is still draining.
