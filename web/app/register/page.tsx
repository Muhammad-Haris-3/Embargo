import { get, pct, type Gates, type RegisterPoint } from "@/lib/api";

export const revalidate = 300;

type Register = { points: RegisterPoint[] };

export default async function RegisterPage() {
  const [data, gates] = await Promise.all([
    get<Register>("/v1/queue/register"),
    get<Gates>("/v1/gates"),
  ]);

  return (
    <>
      <h1>The register</h1>
      <p className="lede">
        Every estimate this project has ever committed, with the answer that
        arrived later, and the distance between them.
      </p>

      <p>
        Each estimate was written to an append-only table <strong>before</strong>{" "}
        it was compared against anything, with a digest of the estimator source
        and of its exact inputs. The role that writes them holds{" "}
        <code>INSERT</code> and nothing else, so the ones that turned out badly
        cannot be withdrawn. A register holding only the estimates that worked
        would answer a different question than the one asked.
      </p>

      {gates && !gates.publishable ? (
        <p className="note">
          <strong>These estimates are not published as findings.</strong>{" "}
          {gates.reason}
        </p>
      ) : null}

      {data ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Freeze date</th>
                <th>Q̂ estimated</th>
                <th>Q* realised</th>
                <th>Error</th>
                <th>Mature</th>
              </tr>
            </thead>
            <tbody>
              {data.points.map((p) => {
                const bad =
                  p.relative_error !== null && Math.abs(p.relative_error) > 0.1;
                return (
                  <tr key={p.freeze_date} className={bad ? "censored" : undefined}>
                    <td>{p.freeze_date}</td>
                    <td>{Math.round(p.q_hat).toLocaleString()}</td>
                    <td>
                      {p.q_star_lower === null
                        ? "—"
                        : `≥ ${p.q_star_lower.toLocaleString()}`}
                    </td>
                    <td>
                      <span className={`pill ${bad ? "fail" : "pass"}`}>
                        {p.relative_error === null
                          ? "—"
                          : `${p.relative_error > 0 ? "+" : ""}${pct(p.relative_error)}`}
                      </span>
                    </td>
                    <td>{p.is_mature ? "yes" : "no"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="note">Register unavailable — the API may be waking up.</p>
      )}

      <h2>Why Q* is written with a ≥</h2>
      <p>
        Q* is the realised queue, counted from today&apos;s record, in which
        every trial that has since posted has disclosed both of its dates. It is
        a <strong>lower bound and never the truth</strong>: a trial submitted
        before the freeze date that has <em>still</em> not posted is invisible
        today exactly as it was invisible then. The bound tightens as postings
        arrive.
      </p>
      <p>
        An estimate falling <em>below</em> Q* has contradicted something already
        on the table, and counts as a failure at any date, mature or not.
      </p>

      <p className="note">
        The tolerance fixed in advance was 10%. The errors here reach 90%, in
        both directions, which is why the queue figure is withheld. The cause is
        the estimator&apos;s load-bearing assumption — that the wait distribution
        does not depend on when a trial was submitted — and the data says it
        does.
      </p>
    </>
  );
}
