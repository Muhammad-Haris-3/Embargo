import Link from "next/link";
import { get, getQueueCurrent, type Cohorts, type Gates, type Status } from "@/lib/api";

export const revalidate = 300;

/**
 * The front page leads with the number that is not there.
 *
 * FR-32 requires refused and failed results to be published with the same
 * prominence as passing ones. Here the refusal is the most prominent thing on
 * the site, because a project whose headline is an absence should not bury the
 * absence beneath the figures that happened to work out.
 */
export default async function Home() {
  const [status, gates, cohorts, withheld] = await Promise.all([
    get<Status>("/v1/status"),
    get<Gates>("/v1/gates"),
    get<Cohorts>("/v1/waits/cohorts"),
    getQueueCurrent(),
  ]);

  const quotable = cohorts?.cohorts.filter((c) => c.quotable) ?? [];
  const quotableRange =
    quotable.length > 0
      ? `${quotable[0].year}–${quotable[quotable.length - 1].year}`
      : null;

  return (
    <>
      <h1>The result exists. You cannot read it yet.</h1>
      <p className="lede">
        When a clinical trial finishes, its sponsor submits the results to
        ClinicalTrials.gov. They are not published on submission. They enter a
        quality-control review, and become readable when they clear it. The law
        is satisfied at submission. Medicine is only served at posting.
      </p>

      <div className="withheld">
        <span className="label">Results in the queue right now</span>
        <div className="figure">Withheld</div>
        {withheld ? (
          <p>{withheld.reason}</p>
        ) : (
          <p>
            The primary outcome is not published. All three preregistered gates
            must pass before any queue estimate appears here.
          </p>
        )}
        <p>
          <Link href="/register">See the estimates and how wrong they were →</Link>
        </p>
      </div>

      <p>
        A trial under review is <strong>indistinguishable from one that has
        reported nothing at all</strong>. The registry publishes nothing about it
        while it waits, and discloses the submission date only once it posts.
        Measured on 2026-08-30: the counts of records carrying a submit date, a
        QC date and a post date are identical, and none of 120 sampled
        completed-but-unposted trials exposed a pending submission.
      </p>

      <p>
        So the number above cannot be counted. It has to be estimated, and the
        estimate has to be marked against dates whose answer has since been
        disclosed. <strong>Ours does not pass that test yet</strong>, so nothing
        is published.
      </p>

      <h2>What is known</h2>
      <p>
        Once a wait is over it is measurable, and 79,892 of them are. From mature
        submission cohorts{quotableRange ? ` (${quotableRange})` : ""}:
      </p>

      <div className="stat-row">
        <div className="stat">
          <span className="n">
            {quotable.length > 0 ? `${quotable[Math.floor(quotable.length / 2)].median_days} d` : "—"}
          </span>
          <span className="k">Typical cohort median</span>
        </div>
        <div className="stat">
          <span className="n">{status ? status.trials.toLocaleString() : "—"}</span>
          <span className="k">Trials collected</span>
        </div>
        <div className="stat">
          <span className="n">{status ? status.estimates_committed : "—"}</span>
          <span className="k">Estimates committed</span>
        </div>
      </div>

      <p>
        <Link href="/cohorts">The full cohort table →</Link>
      </p>

      <h2>The gates</h2>
      <p>
        Three checks were fixed in advance, before any estimator existed. All
        three must pass before the primary outcome is computed at all.
      </p>

      {gates ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Gate</th>
                <th>Verdict</th>
                <th>Failed</th>
                <th>Checked</th>
              </tr>
            </thead>
            <tbody>
              {gates.gates.map((g) => (
                <tr key={g.gate}>
                  <td>{g.gate.replace(/_/g, " ")}</td>
                  <td>
                    <span className={`pill ${g.passed ? "pass" : "fail"}`}>
                      {g.passed ? "pass" : "fail"}
                    </span>
                  </td>
                  <td>{g.n_failed}</td>
                  <td>{g.n_checked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="note">Gate results unavailable — the API may be waking up.</p>
      )}

      <p className="note">
        The build is red on purpose. A green badge while a gate fails would mean
        a finding had been computed after its own validation failed, which is the
        one outcome the preregistration exists to make impossible.
      </p>

      <footer>
        Data from ClinicalTrials.gov, collected daily.{" "}
        {status?.last_collection?.registry_data_timestamp
          ? `Registry snapshot ${status.last_collection.registry_data_timestamp.slice(0, 10)}.`
          : null}{" "}
        No queue estimate is published.
      </footer>
    </>
  );
}
