# Embargo — M0 Spec: Foundation, and Starting the Clock

**Milestone:** M0
**Date:** 2026-08-30
**Status:** In progress

---

## 1. Exit criterion

> Repo, CI, schema, and preregistration committed. The collector runs daily
> against the live registry and writes to an append-only store. The source is
> characterised in `artifacts/source_facts.json`, including the two properties
> the whole design rests on.

M0 is not a pipeline milestone. It is the milestone where **the clock starts**,
and it is urgent for a reason no later milestone can repair.

The queue is not observable in arrears. A result sitting in review this morning
is invisible this morning, and the only way to know what the registry looked
like on a particular day is to have been there on that day. M1 can backfill
every posting that has already happened. **Nothing can backfill a day the
collector did not run.**

---

## 2. What M0 must establish

Four properties, each of which can fail and say so. Two of them, if they fail,
end the project as designed — which is the point of testing them first.

### 2.1 Invisibility — the premise

**Claim:** a results record under review cannot be found through the public API.

Asked two independent ways, because a single query returning nothing is more
often a bad query than a fact about the world:

1. Count records carrying a results submit date, a QC date, and a post date. If
   the search index admitted pending records, the submit count would exceed the
   post count.
2. Sample completed trials with no posted results and read each live record. If
   the record exposed a pending submission, it would be visible here.

**Result, 2026-08-30:**

| | |
|---|---|
| submit / QC / post counts | 79,892 / 79,892 / 79,892 — identical |
| unposted records sampled | 60 |
| …exposing a submit date | **0** |
| unposted completed cohort, 2024-01 to 2025-03 | 21,829 |

**Passed.** The queue is invisible. If this had failed, `Qhat` would be
unnecessary and the project would become a much smaller reporting exercise —
which would have been worth knowing in week one rather than at M4.

### 2.2 Disclosure — the mechanism

**Claim:** once a record posts, it reveals the revisions it made while waiting.

Everything downstream depends on this. Gate 3 marks `Qhat(D)` against `Qstar(D)`,
and `Qstar` exists only because a posted record retroactively discloses when it
was submitted and what it did in between. `PREREGISTRATION.md` lists the failure
of this property under *What would falsify the thesis*.

**Method:** for recently posted records, fetch the revision history and count
those carrying results-module revisions dated between submission and posting.

**Result, 2026-08-30:** 40 records checked, **40 disclosed (100%)**, 0 histories
unavailable. Example: `NCT03661255`, submitted 2026-02-28, posted 2026-08-19 —
172 days, with a results revision inside the gap.

**Passed**, on a sample. The weekly probe re-checks it, because a property that
held once is not a property that holds.

### 2.3 The source will talk to us honestly

**Claim:** the collector can identify itself truthfully and still be served.

This nearly failed, and the way it failed is worth recording.

The registry sits behind a filter that cross-checks the declared user agent
against the client fingerprint. Measured:

| User agent, via httpx | Result |
|---|---|
| `python-httpx/0.28.1` (library default) | 200 |
| `Embargo/0.1.0` | **403** |
| `Embargo/0.1.0 (+https://github.com/…)` | **403** |
| `Mozilla/5.0 (compatible; Embargo/0.1.0; +https://…)` | **403** |
| `Embargo/0.1.0 (+https://github.com/…) python-httpx/0.28.1` | 200 |

The same custom strings are served without complaint to `curl` and to
`urllib` — so the rule is not "unknown clients are banned", it is **"do not
claim to be something other than what you are."** A request that fingerprints as
httpx while calling itself Embargo is refused; so is one dressed as a browser.

The resolution is to state both facts rather than to pick one: the project and
its contact, and the library actually making the request. That is strictly more
accurate than the library default, which identifies the client and says nothing
about who is calling. The browser-shaped string stays refused, and is not used.

**Passed**, and recorded here because a future maintainer hitting a wall of 403s
will otherwise reach for the browser string.

### 2.4 The shape of the thing, provisionally

Not an exit criterion. Recorded so that M1 has something to contradict.

| Wait, submission to posting | Days |
|---|---|
| median | 104.5 |
| p75 | 288 |
| p90 | 686 |
| p99 | 1,842 |
| max | 5,683 |
| share over 180 days | 35.4% |
| share over 365 days | **21.0%** |
| negative waits | 0 |

n = 500. **This sample conditions on records that posted since 2024, which
over-selects long waits**: a trial submitted in 2010 and posted in 2025 is in
the sample, one submitted in 2010 and posted in 2011 is not. The figures are a
probe and are labelled `SELECTION_BIAS` in the artifact itself. M1 recomputes
them by submission cohort, and the M1 summary is expected to report smaller
numbers.

`MATURITY_DAYS` is fixed at 2555 days on the strength of a p99 in this
neighbourhood. If M1 puts the cohort p99 above 2555, that is an amendment to
`PREREGISTRATION.md`, appended and dated, not an edit.

Also measured: **0 of 60 records carried a month-precision submit or post date.**
The partial-date convention is preregistered anyway, because a convention
adopted after meeting the first awkward record is a convention chosen to taste.

---

## 3. What M0 builds

| Area | Artefact |
|---|---|
| Requirements | `Embargo_SRS_v1.0.md` — FR-1→32, NFR-1→12, M0–M8, R-1→10 |
| **Preregistration** | `PREREGISTRATION.md` — three gates, the freeze grid, and the conventions, fixed before any estimate exists |
| Constants | `embargo/preregistration.py`, bound to the document in both directions by `tests/test_preregistration.py` |
| Schema | `sql/001`–`003` — landing, register, roles and grants |
| Source client | `embargo/ctgov.py` — the documented API and the history route, with the difference between them documented |
| Collector | `embargo/ingest.py` — postings sweep and budgeted history sweep, both idempotent |
| Probe | `embargo/probe.py` — the five checks above, re-runnable weekly |
| Run log | `embargo/runlog.py` — every run, including the failures |
| CI | `.github/workflows/ci.yml` — offline suite, lint, and append-only tests against a real Postgres |
| Schedule | `.github/workflows/collect.yml` — daily at 07:00 UTC |

---

## 4. Exit checklist

- [x] Preregistration committed before any estimate exists
- [x] Constants bound to the document in both directions, enforced by a test
- [x] Schema applied; migration is idempotent
- [x] Offline suite passes on a fresh clone with no network and no database
- [x] Invisibility measured and passed
- [x] Disclosure measured and passed
- [x] Source will serve an honest user agent
- [x] Probe artifact committed
- [x] Append-only tests run green against a real Postgres in CI
- [ ] Collector has completed one unattended daily run
- [ ] Seven consecutive daily runs with no gap in the run log

The append-only box was ticked on 2026-08-30: CI's `database` job provisions
through `embargo.bootstrap` and runs `tests/test_append_only.py` as
`embargo_app`, 10 passed, with the workflow failing the build if those tests
*skip* rather than run.

The last two need a scheduler and a calendar, not more code. The first
scheduled run fires at 07:00 UTC on 2026-08-31.

---

## 5. What M0 deliberately does not do

- **No wait is computed for publication.** The probe figures are labelled a
  probe, in the artifact and in this document.
- **No queue is estimated.** `Qhat` does not exist until M4, after three gates.
- **No sponsor is named**, except as an example of a record structure.
- **No finding is claimed.** M0 establishes that the question can be asked.
