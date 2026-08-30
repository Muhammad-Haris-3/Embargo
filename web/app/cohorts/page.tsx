import { days, get, pct, type Cohorts } from "@/lib/api";

export const revalidate = 300;

export default async function CohortsPage() {
  const data = await get<Cohorts>("/v1/waits/cohorts");

  if (!data) {
    return (
      <>
        <h1>The wait, by cohort</h1>
        <p className="note">
          Unavailable. The API may be waking up, or no cohort snapshot has been
          published yet.
        </p>
      </>
    );
  }

  const quotable = data.cohorts.filter((c) => c.quotable);

  return (
    <>
      <h1>The wait, by cohort</h1>
      <p className="lede">
        How long results spent between being submitted and being readable,
        grouped by the year they were submitted.
      </p>

      <p>
        Grouping by submission year removes one bias and exposes another. A
        cohort can only show the trials that have <em>emerged</em>; the ones
        still in review are invisible. So a recent cohort displays only its fast
        members and its median is biased <strong>downward</strong>. Those rows
        are shown, greyed, and marked not quotable — the shape of the censoring
        is the thing this project is about, and hiding it would be worse than
        showing it.
      </p>

      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Cohort</th>
              <th>n</th>
              <th>Median</th>
              <th>p90</th>
              <th>&gt; 1 year</th>
              <th>Quotable</th>
            </tr>
          </thead>
          <tbody>
            {data.cohorts.map((c) => (
              <tr key={c.year} className={c.quotable ? undefined : "censored"}>
                <td>{c.year}</td>
                <td>{c.n_observed.toLocaleString()}</td>
                <td>{days(c.median_days)}</td>
                <td>{days(c.p90_days)}</td>
                <td>{pct(c.share_over_365d)}</td>
                <td>
                  <span className={`pill ${c.quotable ? "pass" : "fail"}`}>
                    {c.quotable ? "yes" : "censored"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="note">
        <strong>n is a lower bound in every row</strong>, including the quotable
        ones. It counts the trials from that cohort which have posted. Those
        still in review cannot be seen or counted, which is the premise of the
        whole project.
        {data.maturity_days
          ? ` A cohort is mature ${data.maturity_days.toLocaleString()} days after 31 December of its year — measured from the end, because a trial submitted in December had the least time of anyone in its cohort.`
          : null}
      </p>

      {quotable.length > 0 ? (
        <p className="age">
          Quotable cohorts: {quotable[0].year}–{quotable[quotable.length - 1].year}.
          Snapshot computed {data.computed_at.slice(0, 10)}.
        </p>
      ) : null}
    </>
  );
}
