# Deploying Embargo

Three pieces, matching GridCast: **Neon** holds the warehouse, **Render** serves
the read-only API, **Vercel** serves the site.

```
Vercel (web/)  ──►  Render (api/)  ──►  Neon
Next.js             FastAPI             PostgreSQL 18
                    reads only          embargo_api: SELECT only
```

GitHub Actions collects into Neon directly and never touches Render or Vercel.

---

## Which credential goes where

This is the part worth getting right, because two of the three roles must never
meet the internet.

| Role | Holds | Lives |
|---|---|---|
| `neondb_owner` | everything | a maintainer's shell, for one command at a time. **Never** in `.env`, CI, Render or Vercel |
| `embargo_app` | `INSERT`, `SELECT` | the `EMBARGO_DSN` GitHub secret, used by the collector |
| `embargo_api` | `SELECT` | the `EMBARGO_READER_DSN` variable in the Render dashboard |

The API refuses to fall back to `EMBARGO_DSN` when `EMBARGO_ENV=production`. If
it could reach for the collector's credential, the append-only guarantee would
rest on the API never *choosing* to write, rather than on its being unable to.
`tests/test_api_credentials.py` holds that in place.

---

## 1. The API, on Render

`render.yaml` is a blueprint. In the Render dashboard: **New → Blueprint**,
point it at the repository, and it reads the file.

It sets `EMBARGO_ENV=production` and pins Python. **You set one variable by
hand, in the dashboard, never in the file:**

```
EMBARGO_READER_DSN = postgresql://embargo_api:...@ep-....neon.tech/neondb?sslmode=require&channel_binding=require
```

That is the second string `embargo.bootstrap` printed. If you no longer have it:

```bash
$env:EMBARGO_ADMIN_DSN = "<neon owner string>"
python -m embargo.bootstrap --admin-dsn $env:EMBARGO_ADMIN_DSN --rotate
```

which prints both roles again, and invalidates the old passwords — so the
`EMBARGO_DSN` GitHub secret needs updating too if you rotate.

**Region is `ohio` to match Neon's `us-east-2`.** Every request is a database
round trip; splitting them across the Atlantic adds ~100ms each on an instance
that is already cold-starting.

Verify: `https://<service>.onrender.com/health` returns `{"status":"ok"}`, and
`/v1/status` returns row counts with `readonly_role_in_use: true`.

## 2. The site, on Vercel

**Root directory `web/`.** Framework preset Next.js; the rest is detected.

One environment variable:

```
NEXT_PUBLIC_API_BASE_URL = https://<service>.onrender.com
```

It is `NEXT_PUBLIC_` because pages fetch at render time and the value is not a
secret — the API is public and read-only.

## 3. The free tier will look broken, and is not

Render's free instance sleeps after inactivity, so the first request of the day
can take **30+ seconds** while the container wakes. `web/lib/api.ts` returns
null rather than throwing, and each page renders "unavailable — the API may be
waking up" beside whatever else it has. A cold start must not look like an
outage.

## 4. What is not deployed, and will not be

The collector. It runs in GitHub Actions on a schedule, writes to Neon
directly, and has no HTTP surface. Nothing about collection depends on Render
or Vercel being up, which is deliberate: a day the collector misses cannot be
recovered, and it should not be able to fail because a web host did.
