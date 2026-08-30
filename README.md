# Embargo

**The result exists. You are not allowed to read it yet, and nobody is counting
how many there are.**

When a clinical trial finishes, its sponsor submits the results to
ClinicalTrials.gov. Those results are not published on submission. They enter a
quality-control review, and they become readable when they clear it. The law is
satisfied at submission. **Medicine is only served at posting.**

Embargo watches the registry every day, measures how long results spend between
those two moments, and estimates how many are sitting in that gap right now —
a number the registry cannot be asked for, because a result under review is
indistinguishable from one that was never submitted at all.

> **Status: M0, collecting.** No queue estimate is published yet, and no wait is
> reported as a finding. [`PREREGISTRATION.md`](PREREGISTRATION.md) fixes the
> three gates, the freeze grid and the conventions that have to be cleared
> first, and all of them were written before the estimator existed.
> [`Embargo_M0_Spec.md`](Embargo_M0_Spec.md) records what M0 has established so
> far, including the two properties that could have ended the project.

---

## The problem, in one example

A trial of a drug you may be taking completes. In February its sponsor submits
the results — the full record, every outcome, every adverse event.

Nothing happens.

A doctor deciding whether to prescribe it searches the registry in June and
finds a completed trial with no results. So does a systematic reviewer pooling
the evidence. So does a patient. All three conclude the same reasonable thing:
this trial has not reported.

It has. The results have existed since February. They are in a review queue, and
the queue is not visible.

In March of the following year the results post, and the record now shows —
retroactively — that they were submitted thirteen months earlier. The evidence
was complete the whole time. **The review was not the delay anyone knew about,
because for its entire duration there was nothing to see.**

## Why it can be checked rather than argued

The tempting version of this project asserts a hidden number and asks to be
believed. This one does not have to.

**The truth arrives on its own schedule, forever.** Freeze a date in the past and
estimate the queue as it stood, using only what was visible then. Then wait:
every trial that posts afterwards discloses its own submission date, and so
tells you whether it was in that queue and how long it had been there. The
estimate gets marked against an answer nobody had to assemble.

That answer is a **lower bound**, not the truth — a trial submitted before the
freeze date that still has not posted is invisible today exactly as it was
invisible then — and it is named `q_star_lower` in the schema so that it cannot
quietly become "the truth" in a later paragraph. The bound tightens as postings
arrive.

**The deliverable is not the queue estimate. It is the error of that estimate
against the dates where the answer has since been disclosed** — and the
tolerance it has to clear was written down first.

## What M0 established

Full record in [`Embargo_M0_Spec.md`](Embargo_M0_Spec.md) and, as measured
output, [`artifacts/source_facts.json`](artifacts/source_facts.json). Each item
is measured, and two of them decided whether the project was possible.

| | |
|---|---|
| **The queue is invisible, confirmed two ways** | The counts of records carrying a submit date, a QC date and a post date are all **79,892** — identical, because the index admits a record only once it has posted. And 0 of 60 sampled completed-but-unposted records exposed a pending submission |
| **A posted record discloses its own wait** | 40 of 40 recently posted records carried results revisions dated between submission and posting. This is the mechanism every later validation rests on, and its failure is listed under falsification |
| **21,829 completed trials** have no posted results for primary completions in a single 15-month window | The population the queue is drawn from is not small |
| **The source refuses a client that misrepresents itself** | `Embargo/0.1.0` alone gets 403 from httpx; so does a browser-shaped string. `Embargo/0.1.0 (+contact) python-httpx/0.28.1` is served. The rule is not "no unknown clients", it is "do not claim to be something you are not" |
| **Provisionally, the median wait is around 100 days** | And 21% exceed a year. On a sample that knowingly over-selects long waits, labelled `SELECTION_BIAS` in the artifact, and expected to shrink when M1 recomputes it by cohort |
| **0 of 60 records used month-precision dates** | The partial-date convention is preregistered anyway. A convention adopted after meeting the first awkward record is a convention chosen to taste |

### One check worth singling out

The user-agent finding is not trivia. The obvious reaction to a wall of 403s is
to send a browser string, and that specific string is refused while an honest
one that names both the project and the library is served. The filter is
enforcing exactly the norm this project would want to follow anyway, and
`embargo/config.py` says so at the point where a future maintainer will be
tempted.

## How the record stays honest

| Mechanism | What it prevents |
|---|---|
| **An observation is a new row.** `(nct_id, content_sha256)` is the primary key; there is no column to overwrite | A store where "we kept what we saw" is a promise made by careful code |
| **The writer role holds `INSERT` and `SELECT` and nothing else** — by `REVOKE`, not convention. `tests/test_append_only.py` connects as that role and asserts `UPDATE` raises | An append-only claim nobody ever tried to violate |
| **`CHECK (committed_at::date >= freeze_date)`** on the estimate register | Backdating — committing an estimate for a date whose data cannot exist yet |
| **Gates before findings.** Three gates must pass before the primary outcome is computed at all | A robustness check run afterwards, on a result someone already likes |
| **A fixed seed for the Gate 1 sample** | Redrawing the sample until it passes |
| **Constants asserted against the preregistration in both directions** | A document that states one threshold while the code uses another — and a constant added to the code that was never written down |
| **Every version cached on first sight** | An undocumented endpoint being withdrawn and taking the evidence with it |
| **Coverage published beside every rate** | A gap in collection reading as a period in which nothing was posted |

## Architecture

```
ClinicalTrials.gov  v2 API (documented)      /api/int history (undocumented)
        │  keyless, daily dataTimestamp             │  the point-in-time primitive
        ▼                                           ▼
GitHub Actions — daily 07:00 UTC, backfill, weekly probe    idempotent · budgeted · run-logged
        ▼
landing        raw payloads, insert-if-changed  +  record_versions
        ▼
reconstruction what was knowable on date D          (M2, knowability-guarded)
        ▼
estimator      right-censored wait model ──► Qhat   (M4)
        │                                     │
        │                                     ▼
        │                          register  append-only, committed before marking
        ▼                                     ▼
gates 1·2·3 ─────────────────────────────► marking against Qstar (lower bound)
        ▼
FastAPI (read-only) ──► Next.js
```

The API reads precomputed rows and **never estimates**. Estimation runs offline
in GitHub Actions. That split keeps the service inside a free-tier container and
is also simply the correct production pattern.

## Running it

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The offline suite needs no network and no database. To characterise the live
source — about 60 API calls, politely throttled:

```bash
EMBARGO_CONTACT="https://github.com/Muhammad-Haris-3/Embargo" python -m embargo.probe --sample 60
```

To collect, with a Postgres to write to:

```bash
cp .env.example .env   # then set EMBARGO_DSN and EMBARGO_CONTACT
python -m embargo.migrate
python -m embargo.ingest --job daily
```

## Deploying it

The database is the only thing that cannot be provisioned from this repository.
Create an empty Postgres — Neon's free tier is what GridCast runs on. In the
Neon console, click **Connect** on the project dashboard and **turn the
connection pooling toggle off**: the pooled endpoint runs PgBouncer in
transaction mode, where the session-level features that role creation and DDL
rely on are unavailable. Copy the direct string, the one without `-pooler` in
the hostname, and use it whole — the database is called `neondb`, and editing
that part of the string is the first thing that goes wrong.

```bash
python -m pip install -e ".[db]"
python -m embargo.bootstrap --admin-dsn "postgresql://neondb_owner:PW@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
```

`bootstrap` applies the schema, creates the two **login** roles as members of
the NOLOGIN groups that hold the grants, and prints their connection strings
once. It writes nothing to disk and sends nothing anywhere. Set the writer
string as the `EMBARGO_DSN` secret and the owner string as `EMBARGO_ADMIN_DSN`:

```bash
gh secret set EMBARGO_DSN --repo Muhammad-Haris-3/Embargo
```

**Only the writer string.** The owner credential is used once, from your
machine, by `bootstrap`, and never stored in CI. A daily workflow holding owner
rights could `UPDATE` or `DELETE` anything, and the append-only guarantee would
be a sentence in this README rather than a property of the system.

Then start it, and check the run log:

```bash
gh workflow run collect.yml --repo Muhammad-Haris-3/Embargo -f job=backfill
```

From then on it runs itself at 07:00 UTC. **The backfill can be run at any time;
the daily runs cannot be caught up.** A day the collector does not run is a day
whose queue is gone.

## Documents

| | |
|---|---|
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | The gates, the grid, the conventions. Fixed before the estimator existed |
| [`Embargo_SRS_v1.0.md`](Embargo_SRS_v1.0.md) | FR-1→32, NFR-1→12, M0–M8, R-1→10 |
| [`Embargo_M0_Spec.md`](Embargo_M0_Spec.md) | What M0 must establish, and what it found |
| `METHODS.md` | Every convention, and the exploratory work, labelled as such — from M1 |
| `DECISION_MEMO.md` | The finding in two pages, no technical background needed — from M8 |

---

## What this project does not claim

Review exists because a results record nobody has checked is not usable
evidence. The delay may well be the price of the record being worth reading, and
**this project measures the delay rather than judging it.** It does not claim the
registry is failing, it does not name a sponsor as non-compliant, and it does
not infer intent from a date.
