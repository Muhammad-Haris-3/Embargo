# Embargo — M5 Summary: The Read-Only API

**Milestone:** M5
**Date:** 2026-08-30
**Status:** Complete, pending one migration that needs the owner credential.

| | |
|---|---|
| Repository | https://github.com/Muhammad-Haris-3/Embargo |
| Run locally | `uvicorn api.main:app --reload` |

---

## 1. Exit criterion

> Read-only API over precomputed rows; deployed skeleton green.

Met in code and verified against the live warehouse. Deployment is not done —
there is no hosted URL yet.

---

## 2. The endpoint that refuses

`GET /v1/queue/current` is the primary outcome: how many results are in the
queue today. It returns **409** and says why.

```json
{
  "published": false,
  "reason": "The primary outcome is withheld because estimator_recovers failing.
             PREREGISTRATION.md requires all three gates to pass before any
             queue estimate is published.",
  "failing": ["estimator_recovers"],
  "see": "Embargo_M4_Summary.md"
}
```

**The endpoint exists and refuses, rather than not existing.** A missing route
reads as an unfinished feature. A 409 naming the failing gate is the
preregistration doing its job in public, on every request, where anyone can see
it.

That rule could have been honoured by remembering not to add the endpoint.
It is honoured by `api/gating.py`, a function the route calls every time,
because a rule that depends on nobody forgetting is not a rule.
`tests/test_api_gating.py` holds it in place with the cases that matter:

- a gate that has **never run** counts as not passed — otherwise an empty
  `gate_results` table would read as "all zero gates pass";
- an **earlier pass does not rescue a later failure**;
- an **unknown gate** cannot count towards the three;
- each of the three can individually block, checked by parametrised test.

## 3. What it serves

| Endpoint | |
|---|---|
| `GET /health` | Liveness, deliberately without touching the database |
| `GET /v1/status` | Row counts, last collection, whether the outcome is publishable |
| `GET /v1/gates` | Every gate's latest verdict and the consequence |
| `GET /v1/waits/cohorts` | The M1 cohort table, `quotable` on every row |
| `GET /v1/queue/register` | Every committed estimate with the bound it was marked against |
| `GET /v1/queue/current` | **409, withheld** |
| `GET /v1/coverage` | Collection days, so a gap is visible rather than inferred |

Live output from `/v1/status` against the warehouse:

```json
{"landing_rows": 79892, "trials": 79892, "record_versions": 74400,
 "version_payloads": 200, "estimates_committed": 18,
 "primary_outcome_publishable": false, "readonly_role_in_use": true}
```

## 4. Three design decisions

**It never computes.** FR-26. Estimation runs offline against the whole
warehouse; a request that triggered it would make the answer depend on when it
was asked for, and would put a statistical method inside a small container on a
stranger's schedule. `/v1/waits/cohorts` reads `mart_wait_cohorts`, written by
`embargo.waits --publish`.

**Marts are append-only too.** There is no refresh-in-place, because the writer
role holds `INSERT` and nothing else. A recomputation is a new snapshot stamped
with the moment it was computed and readers take the latest — which also means
a figure the site once served can always be found again.

**`quotable` travels with the data.** An immature cohort's median is a lower
bound, and a consumer must not be able to pick up the number without also
picking up the reason. Same for `n_is_lower_bound` and
`q_star_is_a_lower_bound`.

## 5. Two defects found by running it

**A 500 on a missing mart.** `/v1/waits/cohorts` returned Internal Server Error
because `mart_wait_cohorts` does not exist yet. A mart nobody has migrated is a
deployment state, not a server fault, and it now answers 503 naming the file to
apply.

**`worst_diff` was null on a gate that missed by 90%.** Gate 3 accumulated the
worst error only where the tolerance test was reached, and both mature dates
failed earlier, on the lower-bound check. It now accumulates over every point
examined.

## 6. Outstanding

`sql/004_marts.sql` has not been applied. Migration needs the owner credential,
which by design exists only on the maintainer's machine and never in CI — so
this is a step that cannot be automated away, and that is the intended
trade-off rather than an oversight.

```bash
python -m embargo.migrate            # with EMBARGO_ADMIN_DSN set to the Neon owner string
python -m embargo.waits --publish
```

## 7. Next

**M6: the application.** The live queue view is the one thing it cannot show,
so the front page becomes the wait by cohort, the gate verdicts, the register
with its errors, and coverage — with the withheld figure stated plainly rather
than omitted.
