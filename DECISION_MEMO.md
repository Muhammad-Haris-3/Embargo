# Decision Memo

**What Embargo set out to measure, what it found, and what it refused to
publish.**

Two pages. No technical background needed.

---

## The thing this is about

When a clinical trial finishes, the people who ran it send the results to
ClinicalTrials.gov — the public registry doctors, researchers and patients
check. Those results are not published when they arrive. They go into a
quality-control review first, and become readable only when they come out.

While a result is in that review, **the registry shows nothing at all**. A trial
whose results are sitting in the queue looks exactly like a trial that never
reported. There is no "pending" marker, no submission date, nothing.

So a doctor who searches in June for a trial whose results were delivered in
February finds a completed study with no results, and reasonably concludes it
never reported. It did. The evidence has existed the whole time and cannot be
read.

## What was found

**Results wait a long time, and the waits are now measured rather than guessed.**

Across 26,984 waits from trials that submitted between 2008 and 2016 — old
enough that essentially all of them have come out the other side:

| | |
|---|---|
| Half of results waited longer than | **81 days** |
| One in ten waited longer than | **499 days** |
| Share that waited more than a year | **13.6%** |

These figures are measured, not estimated. Once a wait is over, both of its
dates are on the public record, so this part needed no modelling at all — only
the observation that nobody had ever put the two dates together.

**The queue is real and large.** At any past date we can now count a lower
bound on how many results were sitting in review. On 30 June 2016 it was **at
least 2,563 trials**. On 30 June 2024, **at least 3,960**. Both are floors, not
totals — a trial that submitted before those dates and still has not come out
remains invisible today exactly as it was then.

## What was not found, and is not published

**The number this project was built to produce does not appear anywhere.**

The question was: *how many results are in the queue right now?* That cannot be
counted, because today's queue is invisible by construction. It has to be
estimated, and an estimate is worth nothing unless you can show it works.

So the design fixed, in advance and in writing, how it would be checked: take a
date in the past, estimate the queue as it stood using only what was visible
then, and compare against the answer that has since come out. Three such checks
were written down before any estimator existed, along with the rule that all
three must pass before any number is published.

**Two passed. The third failed.** The estimator missed by as much as 90%
against a tolerance of 10%, in both directions, at six of nine test dates.

The consequence was also written down in advance, and it holds: **no queue
figure is published.** The website says "Withheld" where the number would be,
and names the failing check. Not as a placeholder — the page asks the live
system on every visit whether it is allowed to show a number, and is told no.

## Why it failed, which is more interesting than the failure

The estimator assumed the wait behaves the same way over time. It does not.

That assumption was written into the code as a stated, load-bearing assumption
*before* the check was run — and the check is what proved it wrong. The waits
vary far more year to year than the method allowed for, so a single average
applied to a period that departed from it overshoots or undershoots depending
on the direction of the departure. Hence errors both ways.

An expectation that turned out wrong is worth recording too. The failure looked
exactly like a known limitation elsewhere in the method — a safety cut-off that
discards the newest submissions. That cut-off discarded **nothing** at any of
the nine dates. The obvious explanation was checked and was false.

## What this is really a demonstration of

The specific finding is that medical evidence sits unreadable for months after
it exists, and nobody counts it.

The general one is harder and matters more: **a system that will not let itself
publish.**

- Every threshold and rule was fixed in a public document before the data was
  touched, and the code is tested against that document in both directions — a
  number in the code that is not in the document fails the build.
- When the document had to change, the original wording stayed on the page and
  the change was appended as a dated amendment. One such amendment made the
  headline **worse**, and was made anyway, because the rule it followed said so.
- Every estimate was written to a table that the writing account has no
  permission to modify or delete. The six failed estimates cannot be withdrawn.
- The public build status is **red on purpose**, and stays red while the check
  fails.

The claim this project asks you to believe is not "the estimate is good." It is
that **the system can be trusted to tell you when it isn't.**

## What would change the answer

The obvious repair is to let the wait distribution vary over time rather than
assuming one shape. It is probably correct, and it has deliberately not been
done — because it is a rule that would be chosen *after* seeing which dates it
fixes. If it is built, it will be recorded as a post-hoc amendment, reported as
weaker evidence than anything fixed in advance, and the failing check will keep
its current definition and keep failing.

Explaining a failure is not passing one.

---

**Status.** Collecting daily since 30 August 2026. 79,892 trials, 74,400 record
revisions. Two of three validation checks pass. No queue estimate is published.

**See it:** [embargo-silk.vercel.app](https://embargo-silk.vercel.app) ·
[the failure in full](Embargo_M4_Summary.md) ·
[what was promised in advance](PREREGISTRATION.md)
