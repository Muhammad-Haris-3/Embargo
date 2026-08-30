# Embargo — Software Requirements Specification v1.0

**Project:** Embargo — Measuring the Results Nobody Can Read Yet
**Author:** Muhammad Haris Khokhar
**Date:** 2026-08-30
**Status:** Draft for approval — M0 in progress

---

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for **Embargo**, a continuously
running data system that measures the interval between a clinical trial's
results being **submitted** to ClinicalTrials.gov and those results becoming
**publicly readable**, estimates the number of results sitting in that interval
on any given day, and marks every estimate against a truth that arrives later on
its own schedule.

The deliverable is a **deployed software product** whose central claim is not
"the registry is slow." It is: *here is a quantity that is structurally
unobservable, here is an estimate of it, and here is the error of that estimate
against the cases where the answer has since been disclosed.*

### 1.2 Scope

Embargo ingests the public ClinicalTrials.gov record daily, keeps every revision
of every record it touches, reconstructs what was knowable on past dates,
estimates the size and composition of the review queue, publishes each estimate
to an append-only register before it can be marked, and grades itself as
postings arrive.

**In scope:** scheduled incremental ingestion with backfill; point-in-time
reconstruction from the record revision history; survival estimation of the wait
under right-censoring; a preregistered three-gate validation suite; an
append-only commitment register; detection of forward edits to primary
completion dates; a public web application; a read-only JSON API; a written
decision memo.

**Out of scope (v1.0):** any registry other than ClinicalTrials.gov; any claim
that a specific sponsor is non-compliant with any law; any claim about the
scientific content of a trial or its results; inference of intent from a record
edit; user accounts; email or SMS alerting; scraping the website rather than
calling the API; predicting whether an individual named trial will post by a
given date as a public-facing product feature.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| **Submission** | The day a sponsor delivered results to the registry — `resultsFirstSubmitDate` |
| **Posting** | The day those results became publicly readable — `resultsFirstPostDate` |
| **Wait** | Posting minus submission, in whole days. The quantity the project is about |
| **The queue** | The set of trials that have submitted and not yet posted, on a given date |
| **`Q(D)`** | The size of the queue on date `D` |
| **`Qhat(D)`** | An estimate of `Q(D)` made from records observable on `D` |
| **`Qstar(D)`** | The realised queue at `D`, computed later from records that have since disclosed both dates. **A lower bound, always** |
| **Invisibility** | The property that the queue cannot be found through the public search index. Measured, not assumed — see §2.1 |
| **Disclosure** | The property that a posted record reveals the revisions it made while waiting. The mechanism every validation depends on |
| **Cohort** | Trials grouped by the year of their submission. Never pooled across differing maturity |
| **Mature** | A cohort for which `MATURITY_DAYS` have elapsed, and which is therefore treated as effectively resolved |
| **Deadline drift** | A forward edit to a primary completion date, which moves the reporting deadline derived from it |
| **Register** | The append-only table of every estimate ever committed. The evidential core |

---

## 2. The problem

### 2.1 What was measured before anything was built

Every number in this section was produced by `python -m embargo.probe` on
2026-08-30 and is recorded in `artifacts/source_facts.json`. They are facts
about the source, not findings about trials.

| Check | Result |
|---|---|
| Records carrying a results **submit** date | 79,892 |
| Records carrying a results **QC** date | 79,892 |
| Records carrying a results **post** date | 79,892 |
| Completed trials with no posted results, sampled | 60 |
| …of those, exposing a pending submission | **0** |
| Completed-but-unposted cohort, 2024-01 to 2025-03 | 21,829 |
| Recently posted records checked for disclosure | 40 |
| …disclosing the revisions made during the wait | **40 (100%)** |

The three counts are identical because the search index admits a record only
once it has posted. The submission date is disclosed **retroactively**. While a
result is under review the registry publishes nothing about it; when it posts,
the whole history appears at once.

**So the queue is invisible while it matters, and fully documented once it is
over.** That single asymmetry generates every requirement below.

### 2.2 Why this has not been done

The data is public and nobody has assembled it, for a specific reason: the
question cannot be asked of the search index. Answering it requires holding
every record's revision history, which means one API call per record across tens
of thousands of records, accumulated over time and cached. Existing compliance
trackers read the current snapshot, which is the one view in which this quantity
does not exist.

---

## 3. Functional requirements

### 3.1 Collection

| ID | Requirement |
|---|---|
| **FR-1** | The system SHALL poll the ClinicalTrials.gov v2 API daily and record the registry's own `dataTimestamp` and `apiVersion` with every run |
| **FR-2** | The system SHALL land raw payloads exactly as received, insert-if-changed by content digest, and SHALL NOT modify a landed payload |
| **FR-3** | The system SHALL record every run in a run log, including runs that fail, so that a gap in collection is visible as a gap and never as a period in which nothing happened |
| **FR-4** | The system SHALL sweep records whose results were first posted since a cutoff, with a lookback window wide enough to absorb a missed run |
| **FR-5** | The system SHALL fetch and store the revision history of every record it lands, under a per-run budget, draining the backlog oldest-first |
| **FR-6** | The system SHALL cache each record version on first sight, so that withdrawal of the undocumented history route cannot destroy data already collected |
| **FR-7** | The system SHALL identify itself in every request with the project, its contact address, and the client library actually making the request |
| **FR-8** | The system SHALL throttle requests and back off with jitter on 429 and 5xx, and SHALL NOT retry a 4xx that is not 429 |

### 3.2 Reconstruction

| ID | Requirement |
|---|---|
| **FR-9** | The system SHALL reconstruct the state of any record as of any past date, from stored versions |
| **FR-10** | The system SHALL distinguish results-module revisions from protocol-module revisions, and SHALL NOT treat protocol churn as evidence of a wait |
| **FR-11** | The system SHALL resolve month-precision dates to the first of the month and SHALL flag every value derived from one |
| **FR-12** | The system SHALL exclude negative waits from every statistic and report their count, and SHALL NOT clamp them to zero |
| **FR-13** | A knowability guard SHALL raise when any reconstruction consumes a value that could not have been held on the date being reconstructed |

### 3.3 Estimation

| ID | Requirement |
|---|---|
| **FR-14** | The system SHALL estimate the wait distribution by submission cohort under right-censoring, treating trials that have not yet posted as censored rather than absent |
| **FR-15** | The system SHALL estimate `Qhat(D)` using only records observable on `D` |
| **FR-16** | The system SHALL compute `Qstar(D)` and SHALL label it a lower bound wherever it appears |
| **FR-17** | The system SHALL commit every estimate to an append-only register before it is marked, with a digest of its inputs and of the method |
| **FR-18** | The system SHALL report cohort coverage beside every rate, so that a tightening bound is never mistaken for a growing queue |
| **FR-19** | The system SHALL estimate queue **composition** — the distribution of elapsed waiting time within the queue — not only its size |

### 3.4 Validation

| ID | Requirement |
|---|---|
| **FR-20** | Gate 1 SHALL verify that reconstructed versions reproduce the API's versions on a seeded sample |
| **FR-21** | Gate 2 SHALL verify that the warehouse's per-year posting counts equal the registry's own counts, exactly |
| **FR-22** | Gate 3 SHALL verify that `Qhat(D)` falls within tolerance of `Qstar(D)` at every mature grid date, and never below it at any grid date |
| **FR-23** | All three gates SHALL run before the primary outcome is computed, and the pipeline SHALL refuse to compute it if any gate fails |
| **FR-24** | Gate results SHALL be written to the database, not asserted in prose |
| **FR-25** | The CI job SHALL fail when a gate fails. A green badge on a failed gate is the defect |

### 3.5 Publication

| ID | Requirement |
|---|---|
| **FR-26** | The API SHALL be read-only, SHALL serve precomputed rows, and SHALL never estimate at request time |
| **FR-27** | The application SHALL show the live queue estimate with its interval, labelled a running quantity and not the primary outcome |
| **FR-28** | The application SHALL show a calibration view of committed estimates against realised bounds, which fills in over time |
| **FR-29** | The application SHALL show recently posted results with the wait each one turned out to have had |
| **FR-30** | The application SHALL show a revision diff for a record whose primary completion date moved, with the version dates either side |
| **FR-31** | The application SHALL state, on every page carrying a number, the date of the data behind it |
| **FR-32** | The application SHALL publish refused and failed gates with the same prominence as passing ones |

---

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| **NFR-1** | The collector SHALL run within GitHub Actions free-tier limits |
| **NFR-2** | The API SHALL run within a 512 MB container; training and estimation run offline |
| **NFR-3** | The warehouse SHALL fit a free-tier Postgres instance for at least 24 months of collection |
| **NFR-4** | The offline test suite SHALL run on a fresh clone with no network and no database |
| **NFR-5** | The writer role SHALL hold `INSERT` and `SELECT` only, enforced by grant, with `UPDATE` permitted on the run log alone |
| **NFR-6** | The append-only guarantee SHALL be tested by attempting the forbidden write as the writer role, and CI SHALL fail if those tests skip |
| **NFR-7** | No credential SHALL appear in source, logs, or artifacts |
| **NFR-8** | Every request SHALL be attributable to this project by its user agent |
| **NFR-9** | A single failed record SHALL NOT end a sweep |
| **NFR-10** | Every published figure SHALL carry its coverage |
| **NFR-11** | Preregistered constants SHALL be asserted against `PREREGISTRATION.md` by the test suite, in both directions |
| **NFR-12** | The application SHALL be legible to a reader with no clinical or statistical background on its first screen |

---

## 5. Milestones

| ID | Exit criterion |
|---|---|
| **M0** | Repo, CI, schema, preregistration committed, collector running daily, source characterised in `artifacts/source_facts.json`. **The clock starts.** See `Embargo_M0_Spec.md` |
| **M1** | Backfill complete. Wait distribution recomputed by submission cohort, replacing the biased probe figures. Coverage published |
| **M2** | Point-in-time reconstruction and the knowability guard. Gate 1 runs |
| **M3** | Census reconciliation. Gate 2 runs |
| **M4** | The estimator: right-censored wait model, `Qhat` and `Qstar`, committed to the register. Gate 3 runs — the milestone the project exists for |
| **M5** | Read-only API over precomputed rows; deployed skeleton green |
| **M6** | The application: live queue, calibration, recent postings, coverage |
| **M7** | Deadline drift: forward-edit detection over stored versions, by sponsor class, with diffs |
| **M8** | `DECISION_MEMO.md` — the finding in two pages, no technical background needed |

Milestones after M0 are ordered by dependency, not by date. **M4 may fail.** If
Gate 3 fails, M5–M6 ship the application with the failure as the headline and no
queue estimate at all, which is what `PREREGISTRATION.md` requires.

---

## 6. Risks

| ID | Risk | Response |
|---|---|---|
| **R-1** | The history route is undocumented and may be withdrawn or rate-limited | Cache every version on first sight (FR-6). Data already collected survives the route. Throttle conservatively; identify honestly |
| **R-2** | The source refuses requests whose user agent does not match the client fingerprint | Measured at M0; the user agent states both the project and the library. A browser-shaped string stays refused, and is not used |
| **R-3** | Disclosure stops holding — a posted record ceases to reveal its wait | The weekly probe re-checks it. `PREREGISTRATION.md` lists it under falsification; if it fails, Gate 3 is unmarkable and that is published |
| **R-4** | `Qstar` is a lower bound and may be mistaken for truth | Named `q_star_lower` in the schema, labelled at every surface, and `Qhat < Qstar` is a Gate 3 failure at any date |
| **R-5** | The queue becomes visible — the registry starts indexing pending submissions | The premise improves and the estimator becomes unnecessary. Published as a finding; the estimate is retained for the period when it was needed |
| **R-6** | Cohort maturity is set too short and immature cohorts leak into Gate 3 | `MATURITY_DAYS` fixed in advance at 2555 days, above the probed p99; M1 rechecks it and a change requires an amendment |
| **R-7** | A collection gap is read as a quiet period | The run log records every run including failures; coverage is published beside every rate |
| **R-8** | The deadline-drift work invites a claim about intent | Out of scope by `PREREGISTRATION.md`; the finding is that a date moved and when, and the forbidden sentence is written down so it can be checked for |
| **R-9** | Warehouse growth outpaces the free tier | Version payloads are the bulk; store the status module rather than whole records once M2 confirms what reconstruction needs |
| **R-10** | The project is mistaken for an attack on the registry | The README says what review is for in its first paragraphs, and `PREREGISTRATION.md` forbids the claim |
