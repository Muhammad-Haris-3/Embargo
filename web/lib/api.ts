/**
 * API access.
 *
 * Every figure on this site comes from the read-only API, which serves
 * precomputed rows and never estimates at request time. Nothing here computes
 * either: if a number is not in a response, the page says so rather than
 * deriving it, because a figure invented in a browser has no provenance.
 *
 * A free-tier container sleeps after inactivity, so the first request of the
 * day can take 30+ seconds to wake it. That is normal, not an outage, and the
 * UI has to say "waking up" rather than "failed" or every cold start looks like
 * a broken deployment.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Cohort = {
  year: number;
  n_observed: number;
  n_is_lower_bound: boolean;
  is_mature: boolean;
  quotable: boolean;
  median_days: number | null;
  p75_days: number | null;
  p90_days: number | null;
  p99_days: number | null;
  max_days: number | null;
  share_over_180d: number | null;
  share_over_365d: number | null;
  negative_waits_excluded: number;
  partial_dates_flagged: number;
};

export type Cohorts = {
  computed_at: string;
  maturity_days: number | null;
  cohorts: Cohort[];
};

export type Gate = {
  gate: string;
  passed: boolean;
  n_checked: number;
  n_failed: number;
  worst_diff: number | null;
  checked_at: string;
};

export type Gates = {
  gates: Gate[];
  publishable: boolean;
  failing: string[];
  never_run: string[];
  reason: string | null;
};

export type RegisterPoint = {
  freeze_date: string;
  q_hat: number;
  q_star_lower: number | null;
  q_star_is_a_lower_bound: boolean;
  relative_error: number | null;
  is_mature: boolean | null;
  committed_at: string;
  method: string;
};

export type Status = {
  landing_rows: number;
  trials: number;
  record_versions: number;
  version_payloads: number;
  estimates_committed: number;
  primary_outcome_publishable: boolean;
  readonly_role_in_use: boolean;
  last_collection: {
    job: string;
    status: string;
    started_at: string;
    finished_at: string | null;
    rows_appended: number;
    registry_data_timestamp: string | null;
  } | null;
};

export type CoverageDay = {
  day: string;
  ok: number;
  failed: number;
  unclosed: number;
  rows_appended: number;
};

export type Coverage = { days: CoverageDay[]; note: string; generated_at: string };

/**
 * Fetch, returning null rather than throwing.
 *
 * A page that renders "unavailable" beside the rest of its content is more
 * useful than one that 500s entirely because a single endpoint is asleep. Each
 * caller decides what an absent section should say.
 */
export async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      next: { revalidate: 300 },
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/**
 * The withheld primary outcome.
 *
 * `/v1/queue/current` answers 409 while any gate fails, and the body carries
 * the reason. A 409 is the expected response, not an error, so it is parsed
 * rather than swallowed.
 */
export type Withheld = {
  published: false;
  reason: string;
  failing: string[];
  never_run: string[];
  see: string;
};

export async function getQueueCurrent(): Promise<Withheld | null> {
  try {
    const res = await fetch(`${API_BASE}/v1/queue/current`, {
      next: { revalidate: 300 },
      headers: { accept: "application/json" },
    });
    const body = await res.json();
    if (res.status === 409) return body as Withheld;
    return null;
  } catch {
    return null;
  }
}

export function days(n: number | null): string {
  return n === null ? "—" : `${n.toLocaleString()} d`;
}

export function pct(x: number | null): string {
  return x === null ? "—" : `${(x * 100).toFixed(1)}%`;
}
