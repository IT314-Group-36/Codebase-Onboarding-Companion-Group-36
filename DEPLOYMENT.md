# Deploying: Neon (database) + Render (backend) + Vercel (frontend)

All three have free tiers. The browser only ever talks to your Vercel URL: Vercel forwards `/api/*` to Render
(`frontend/vercel.json`). That keeps the login cookie first-party, so sign-in works in every browser.

```
browser ──> Vercel (React app)  ──/api/*──>  Render (FastAPI + background jobs)  ──>  Neon (Postgres + pgvector)
```

Background indexing runs inside the Render web service (no Redis, no worker). One repository is indexed at a time.

## Current deployment

| Part | Where | URL |
|---|---|---|
| Frontend | Vercel (Hobby), project `onboarding-companion` | https://onboarding-companion-pearl.vercel.app |
| Backend | Render (free, Docker, Singapore) | https://onboarding-companion.onrender.com |
| Database | Neon (free, Singapore), project `onboarding-companion`, direct connection | not public |

`frontend/vercel.json` forwards `/api/*` to the Render URL above. If the Render service is ever renamed or
recreated, update that host and the three Render variables that mention the Vercel URL.

## 0. Before you start

- The GitHub repo can be public or private, but see the Vercel note below if it belongs to an organization.
- You need: a Gemini (or other LLM) API key, a Cloudflare Workers AI account id + token (embeddings), and
  permission to create a GitHub OAuth app.
- Generate **new** production secrets (do not reuse the ones in your local `backend/.env`):

  ```bash
  cd backend && uv run python -m app.core.security     # prints TOKEN_ENCRYPTION_KEY and SESSION_SECRET
  ```

## 1. Neon (database)

1. Create a project (any region close to your Render region, e.g. AWS Singapore + Render Singapore).
   Keep only **Postgres database** switched on; the other services (Object storage, Functions, AI gateway,
   Realtime, Better Auth) are not used.
2. Open **Connect** and copy the **direct** connection string (host without `-pooler`). It looks like
   `postgresql://user:pass@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`.
   Paste it as `DATABASE_URL` as it is: the app converts the prefix to `postgresql+psycopg://` itself.
3. Nothing else to do: the `vector` extension and all tables are created by the migrations, which run
   automatically every time the Render service starts. If the string ends in `&channel_binding=require`, keep it;
   if Render's logs ever complain about channel binding, remove that part and keep `?sslmode=require`.
4. After the first Render deploy you can check the result in Neon's **SQL Editor**:
   `select table_name from information_schema.tables where table_schema = 'public' order by table_name;`
   should list 13 tables (`alembic_version`, `chunks`, `conversation_messages`, `conversations`, `edges`,
   `explanations`, `files`, `issue_syncs`, `issues`, `repositories`, `symbols`, `task_progress`, `users`).

## 2. Render (backend)

1. **New + > Web Service**. If the repo is not listed, connect GitHub and install the Render GitHub app on the
   organization that owns the repo (an org owner may need to approve it).
2. Settings: **Language: Docker**, **Branch: `main`**, **Region** next to your Neon region,
   **Root Directory: leave blank**, **Dockerfile Path: `backend/Dockerfile`**,
   **Instance type: Free** (make sure the $0 plan is selected, not $7).
3. Under **Advanced**: **Docker Build Context Directory: `./backend`**, **Health Check Path: `/health`**,
   **Auto-Deploy: On Commit**. Leave **Docker Command** and **Pre-Deploy Command** empty (the Dockerfile already
   runs the migrations).
4. Add the environment variables below (**Add from .env** pastes them all at once; no quotes around values),
   then deploy. The container runs `alembic upgrade head` and then starts the API on Render's `$PORT`.
   Migrations print nothing to the log: a healthy start ends with `Uvicorn running on http://0.0.0.0:10000`.
5. Open `https://<service>.onrender.com/health`; it should answer `{"status":"ok"}`. Note the URL.

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon direct connection string |
| `LLM_API_KEY`, `LLM_MODEL` | your LLM key and model (e.g. `google_genai:gemini-3.6-flash`) |
| `EMBED_BACKEND` | `cloudflare` |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | Cloudflare Workers AI credentials |
| `TOKEN_ENCRYPTION_KEY`, `SESSION_SECRET` | the new production secrets from step 0 |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | the **production** GitHub OAuth app (step 4) |
| `FRONTEND_URL` | `https://<your-app>.vercel.app` |
| `GITHUB_REDIRECT_URI` | `https://<your-app>.vercel.app/api/auth/github/callback` (the **Vercel** URL) |
| `COOKIE_SECURE` | `true` |
| `CORS_ORIGINS` | `["https://<your-app>.vercel.app"]` (a JSON list) |
| `LLM_MIN_INTERVAL_SECONDS` | `4` on a free LLM tier, lower on a paid one |

Rate limits and per-user quotas are on by default and need no variables; see "Abuse protection" in
`backend/README.md` to tune them (for example `MAX_TOTAL_CHUNKS` to match your Neon storage).

Leave `ALLOW_LOCAL_REPOS` unset (it must stay false in production). Optional: `GITHUB_TOKEN` (higher GitHub API
rate limit for the issues sync), `MAX_CONCURRENT_INDEXING` (default 1; keep 1 on a 512 MB instance).

## 3. Vercel (frontend)

1. **Add New > Project**, import the repo.
2. Settings: **Root Directory: `frontend`**, Framework **Vite**, Node.js **22.x**
   (`npm run build`, output `dist`; `frontend/package.json` already asks for Node 22).
3. **Before the first deploy, edit `frontend/vercel.json`**: replace `YOUR-RENDER-SERVICE.onrender.com` with your
   real Render host name and commit. Leave `VITE_API_BASE_URL` unset (it defaults to `/api`).
4. Deploy, then copy the production URL (e.g. `https://your-app.vercel.app`) into Render's `FRONTEND_URL`,
   `GITHUB_REDIRECT_URI` and `CORS_ORIGINS`, and redeploy Render if you had used a placeholder.

Organization repos: Vercel's free **Hobby** plan cannot deploy *private* repos owned by a GitHub organization.
Public org repos should work; if Vercel blocks a teammate's commits, deploy from the project owner's account.

## 4. GitHub OAuth app (production)

Create a **separate** OAuth app at https://github.com/settings/developers (keep your localhost one for development):

- Homepage URL: `https://<your-app>.vercel.app`
- Authorization callback URL: `https://<your-app>.vercel.app/api/auth/github/callback`

It must equal `GITHUB_REDIRECT_URI` exactly. Use the Production client id/secret on Render. Sign-in works on the
production domain only, not on Vercel preview URLs.

## 5. Check that it works

1. `https://<service>.onrender.com/health` returns ok.
2. Open the Vercel URL, click **Sign in with GitHub**, and land on the dashboard.
3. Register a small public repository; it should move queued, indexing, ready.
4. Open the module map and Explorer, then ask a question in Q&A and check that the answer streams in.
   (Streaming goes through Vercel's proxy. If answers only appear at the end or time out, see Troubleshooting.)

## Free-tier behaviour to expect

- **Render sleeps** after about 15 minutes without traffic; the next request can take up to a minute. The UI says the
  server may be waking up. Indexing keeps the instance awake while the page polls.
- **A job cut off by a restart or redeploy** is marked *failed* ("interrupted ... Click Re-index") at the next
  startup, and the user clicks Re-index. Avoid deploying while someone is indexing.
- **Neon scales to zero** after about 5 minutes idle; the first query then takes a few seconds (the connect
  timeout is 30 s and stale connections are replaced automatically).
- **Memory:** the free Render instance has 512 MB. Very large repositories can run it out of memory; lower
  `MAX_CHUNKS` or index smaller repos. Git now has a 256 MiB per-process address-space limit on Linux,
  a 200 MiB aggregate disk watchdog, and pre-checkout size checks (100 MiB total / 20 MiB per file).
  Tune `CLONE_MEMORY_BYTES`, `MAX_CLONE_BYTES`, `MAX_CHECKOUT_BYTES` and `MAX_CLONE_FILE_BYTES` if needed;
  keep `MAX_CONCURRENT_INDEXING=1`. The disk watchdog is not a strict filesystem quota, and parsing
  still uses memory in the API process. Strict aggregate disk isolation requires a host-configured quota.
- **Neon storage** is limited (1 GB on the free plan at the time of writing; check Neon's current limits). Each
  indexed repository stores its chunks and vectors. Progress and chat data now have row caps and share
  a 400 MiB application planning budget (`STORAGE_BUDGET_BYTES`) with indexed chunks. Pending answers
  reserve their maximum configured payload before generation. Tune the `MAX_TASK_PROGRESS_*`,
  `MAX_CONVERSATIONS_*`, `MAX_MESSAGES_*` and message-byte settings in `backend/.env.example` as needed.
  No migration or automatic history purge is required. Existing over-limit data blocks growing writes,
  not reads/deletions. This is not a physical database quota: leave headroom for indexes, other derived
  tables and bloat, and monitor actual usage in Neon.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `psycopg2` / "can't load plugin sqlalchemy.dialects:postgresql.psycopg2" | old code reading a plain `postgresql://` URL; this repo converts it, so check the deployed commit |
| Render logs: `connection failed` / SSL errors | wrong `DATABASE_URL`, or the Neon project is suspended; copy the string again from Neon **Connect** |
| Login redirects back to the login page | `FRONTEND_URL`/`GITHUB_REDIRECT_URI` do not use the Vercel domain, `COOKIE_SECURE` is not `true`, or `vercel.json` still has the placeholder host |
| GitHub: "redirect_uri is not associated with this application" | the OAuth app's callback URL differs from `GITHUB_REDIRECT_URI` |
| CORS errors in the browser console | `CORS_ORIGINS` is not a JSON list containing the exact Vercel origin |
| Q&A answers arrive all at once or time out | Vercel's proxy is buffering the stream. Fallback: serve the app and API under one custom domain (`app.` and `api.` subdomains) |
| Repo stays *queued* for a long time | another repository is indexing (one at a time), or the instance restarted: wait, or re-index |
| 502/503 right after opening the app | Render is waking up; retry in a minute |
