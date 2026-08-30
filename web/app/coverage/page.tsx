import { get, type Coverage, type Status } from "@/lib/api";

export const revalidate = 300;

export default async function CoveragePage() {
  const [coverage, status] = await Promise.all([
    get<Coverage>("/v1/coverage"),
    get<Status>("/v1/status"),
  ]);

  return (
    <>
      <h1>Coverage</h1>
      <p className="lede">
        Which days the collector actually ran, because a gap in collection must
        never read as a period in which nothing was posted.
      </p>

      <p>
        The queue is not observable in arrears. A result sitting in review this
        morning is invisible this morning, and the only way to know what the
        registry looked like on a particular day is to have been there on that
        day. <strong>Every day the collector does not run is a day that cannot
        be recovered.</strong>
      </p>

      {status ? (
        <div className="stat-row">
          <div className="stat">
            <span className="n">{status.trials.toLocaleString()}</span>
            <span className="k">Trials</span>
          </div>
          <div className="stat">
            <span className="n">{status.record_versions.toLocaleString()}</span>
            <span className="k">Record revisions</span>
          </div>
          <div className="stat">
            <span className="n">{status.version_payloads.toLocaleString()}</span>
            <span className="k">Cached revisions</span>
          </div>
        </div>
      ) : null}

      {coverage ? (
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Day (UTC)</th>
                <th>Ok</th>
                <th>Failed</th>
                <th>Unclosed</th>
                <th>Rows appended</th>
              </tr>
            </thead>
            <tbody>
              {coverage.days.map((d) => (
                <tr key={d.day} className={d.ok === 0 ? "censored" : undefined}>
                  <td>{d.day}</td>
                  <td>{d.ok}</td>
                  <td>{d.failed}</td>
                  <td>{d.unclosed}</td>
                  <td>{d.rows_appended.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="note">Coverage unavailable — the API may be waking up.</p>
      )}

      <p className="note">
        A day absent from this list is a day nothing ran.{" "}
        <strong>Unclosed</strong> counts runs that started and never finished —
        a job killed mid-run leaves its row open, which is exactly what a
        silently dead scheduled collector should look like from the outside.
      </p>

      {status?.last_collection ? (
        <p className="age">
          Last collection: {status.last_collection.job},{" "}
          {status.last_collection.status},{" "}
          {status.last_collection.rows_appended.toLocaleString()} rows appended.
          {status.last_collection.registry_data_timestamp
            ? ` Registry snapshot ${status.last_collection.registry_data_timestamp.slice(0, 10)}.`
            : null}
        </p>
      ) : null}
    </>
  );
}
