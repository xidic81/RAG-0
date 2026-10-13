# Deploying — Railway (API) and Vercel (web UI)

The FastAPI backend runs on [Railway](https://railway.com) (§1–7); the
Next.js UI in `web/` runs on [Vercel](https://vercel.com) (see
[Web UI on Vercel](#web-ui-on-vercel)). Deploy the API first — the UI needs
its public URL. Pinecone and Groq stay what they are locally: hosted
services the API reaches over the internet.

```
GitHub (main) ──push──▶ Railway project
                         ├── learning_rag_0   FastAPI (uvicorn) ──▶ Pinecone, Groq
                         └── Postgres         tables created by the API on startup
              ──push──▶ Vercel project (Root Directory: web)
                         └── Next.js UI       /api/* ──▶ learning_rag_0
```

Example Live URL: https://learningrag0-production.up.railway.app (interactive API
docs at [`/docs`](https://learningrag0-production.up.railway.app/docs)) This is temporary maybe i will shut this live example one day.

**You need:** a Railway account, the Railway CLI (`npm i -g @railway/cli`),
a Vercel account (for the UI), access to this GitHub repo, and the same
Pinecone and Groq API keys as in your `.env`.

---

## 1. Create the project

1. On railway.com: **New Project → Deploy from GitHub repo →**
   `rizkibyte/learning_rag_0`. Railway creates a service named
   `learning_rag_0` and builds it with Railpack, which detects
   `pyproject.toml` + `uv.lock` and takes the Python version from
   `.python-version`.
2. In the **same project**: **+ Create → Database → PostgreSQL**.
3. On the API service: **Settings → Networking → Generate Domain**.

Postgres must be in the same project *and* environment as the API. A
`${{Postgres.…}}` reference to a service anywhere else — another project,
or a project under a different Railway account — silently resolves to an
empty string (see Troubleshooting).

Link the CLI from the repo folder so later commands know which project
you mean:

```bash
railway login
railway link       # choose the project
railway status     # should list learning_rag_0 (with its URL) and Postgres
```

`railway whoami` shows which account you're logged in as — check it first
if you have more than one.

## 2. Start command — `railway.json`

```json
{
  "build": { "builder": "RAILPACK" },
  "deploy": {
    "startCommand": "uvicorn rag.api:app --host 0.0.0.0 --port ${PORT:-8000}"
  }
}
```

Every part of that command is there for a reason:

- `--host 0.0.0.0` — uvicorn's default, `127.0.0.1`, isn't reachable from
  Railway's proxy.
- `--port ${PORT:-8000}` — Railway tells the app which port to use through
  `$PORT`.
- no `--reload` — that's a development feature (file watching).
- plain `uvicorn`, not `uv run uvicorn` — Railpack already installed the
  dependencies into the image at build time.

Railway is retiring `railway.json` ("Config as Code") in favour of
Infrastructure as Code (`.railway/railway.ts`). Existing files keep working
until **2026-12-01** — run `railway config migrate` before then.

## 3. Variables

Set these on the **API service** (`learning_rag_0` → **Variables**), not on
Postgres. `.env` is gitignored and never reaches Railway, so everything the
app needs must be set here:

| Variable           | Value                        | Notes |
|--------------------|------------------------------|-------|
| `POSTGRES_DSN`     | `${{Postgres.DATABASE_URL}}` | A reference, not a pasted URL — type `${{` and pick from the dropdown. The value field holds only this, no `POSTGRES_DSN=` in front. |
| `PINECONE_API_KEY` | your key                     | |
| `PINECONE_INDEX`   | `rag-chatbot-prod`           | **Not** your local index name — see below. Created automatically on the first upload. |
| `GROQ_API_KEY`     | your key                     | |
| `GROQ_MODEL`       | `openai/gpt-oss-120b`        | |
| `USE_OLLAMA`       | `false`                      | There's no Ollama on Railway. The `OLLAMA_*` variables aren't needed. |

Or from the CLI (single quotes stop your shell expanding `${{…}}`):

```bash
railway variable set --service learning_rag_0 \
  'POSTGRES_DSN=${{Postgres.DATABASE_URL}}' \
  PINECONE_INDEX=rag-chatbot-prod GROQ_MODEL=openai/gpt-oss-120b USE_OLLAMA=false

# secrets: --stdin keeps them out of your shell history (paste, then Enter, Ctrl+D)
railway variable set --service learning_rag_0 --stdin GROQ_API_KEY
railway variable set --service learning_rag_0 --stdin PINECONE_API_KEY
```

Changing variables triggers a redeploy. To check what a reference resolved
to, click the eye icon next to it in the dashboard — `POSTGRES_DSN` should
show a `postgres.railway.internal` URL, not a blank.

**Why a separate Pinecone index.** Postgres holds chunk text; Pinecone holds
only vectors, keyed by chunk id. The vectors in your local index point at
chunk ids that exist only in your *local* Postgres. Share the index and
Railway's searches return those vectors, find no matching rows, and skip
them — `/chat` answers "I couldn't find this in the documents." every time.
It works the other way too: uploads on Railway would leak into your local
results.

## 4. Database tables — automatic

Nothing to do. On startup the API runs `sql/schema.sql`
(`rag.db.init_schema`, called from the FastAPI lifespan in `rag/api.py`).
Every statement is `IF NOT EXISTS`, so on a database that's already set up
it changes nothing. If it fails, the app still starts: the logs show
`schema init failed: …` and `/health` shows why.

If you ever need to run SQL by hand, note that `DATABASE_URL` uses
`postgres.railway.internal`, which only resolves *inside* Railway. From your
machine you need the public URL: enable **Postgres → Settings → Networking →
TCP Proxy**, then use `DATABASE_PUBLIC_URL`:

```bash
psql "<DATABASE_PUBLIC_URL>" -f sql/schema.sql
```
## 5. Load the documents

The Railway database starts empty. Upload through the API — ingestion runs
on Railway, so your machine never needs database access:

```bash
B=<your-public-railway-url>   # from §1 step 3, e.g. https://<service>-production.up.railway.app

# 1. one PDF on its own first: this upload creates the Pinecone index
curl -F "file=@data/pdfs/a-christmas-carol.pdf" $B/documents

# 2. repeat until it shows "ready" (pending → processing → ready, or failed + error)
curl -s $B/documents | python3 -m json.tool

# 3. then the rest (re-uploading the first is a no-op: same file hash)
for f in data/pdfs/*.pdf; do curl -s -F "file=@$f" $B/documents; echo; done
```

Upload one first so the index exists before several ingestions run at
once — otherwise they can race to create it.

Uploaded PDFs are written to the container's disk, which is wiped on every
deploy. That's fine: once a document is `ready`, its text is in Postgres
and its vectors are in Pinecone, and the file itself is never read again.

## 7. Verify

```bash
B=<your-public-railway-url>
curl $B/health
curl $B/documents
curl -X POST $B/chat -H "Content-Type: application/json" \
  -d '{"message": "Who is Ebenezer Scrooge?"}'
curl -X DELETE $B/documents/00000000-0000-0000-0000-000000000000
```

| Check                   | Expected |
|-------------------------|----------|
| `/health`               | `postgres`, `pinecone`, `llm` all `"ok"` |
| `/documents`            | every document `"ready"` |
| `/chat`                 | an answer with `citations` (filename + page) |
| `DELETE` an unknown id  | 404 `document not found` |

---

## Web UI on Vercel

The Next.js app in `web/` deploys to Vercel. It needs the API's public URL
from §1 step 3, so do the Railway part first.

1. On vercel.com: **Add New → Project →** import `rizkibyte/learning_rag_0`.
2. **Root Directory: `web`** (click **Edit** next to it). The repo root is
   the Python API; the Next.js app lives in `web/`. Leave the framework
   (Next.js) and build settings on their defaults.
3. **Environment Variables:** add `API_URL` = your Railway public URL, e.g.
   `https://<service>-production.up.railway.app` (a trailing slash is fine).
4. **Deploy**, then open the Vercel URL. The postgres / pinecone / LLM dots
   in the header should all be green, and the Documents page should list
   what you loaded in §5.

**How it fits together.** The browser only ever calls `/api/...` on the
Vercel domain; the rewrite in `web/next.config.ts` forwards those requests
to `API_URL`:

```ts
const apiUrl = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
// rewrites: /api/:path*  →  ${apiUrl}/:path*
```

The API never sees a cross-origin request, so it needs no CORS setup. And
since FastAPI sends no cache headers, Vercel doesn't cache API responses.

- **`API_URL` is read at build time** — the rewrite is baked into the
  build. After changing it, redeploy (**Deployments → ⋯ → Redeploy**); a
  new value does nothing until then.
- **`.env` files aren't deployed** (`web/.gitignore` excludes them), so the
  value must be set in Vercel. Locally, `API_URL` defaults to
  `http://localhost:8000`; to point your local UI somewhere else, copy
  `web/.env.example` to `web/.env.local` and edit it.
- **Every push to `main` deploys both**: Railway redeploys the API and
  Vercel deploys the UI to production. Vercel also gives other branches and
  pull requests their own preview URLs (those still call the production
  API).

---

## Troubleshooting

For any 500, start with the logs — they have the Python traceback:

```bash
railway logs --service learning_rag_0
```

| Symptom | Cause | Fix |
|---------|-------|-------|
| URL doesn't respond / "Application failed to respond" | uvicorn not listening on `0.0.0.0:$PORT` | start command, §2 |
| `/health` postgres: `connection to server at "127.0.0.1", port 5432 failed` | `POSTGRES_DSN` not set — the app falls back to localhost | set it, §3 |
| `/health` postgres: `invalid connection option "POSTGRES_DSN"` | the value includes the name: `POSTGRES_DSN=${{…}}` | value field holds only `${{Postgres.DATABASE_URL}}` |
| `/health` postgres: `connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed` | the reference resolved to an empty string: no Postgres in this project, a different service name, or a different environment | add Postgres to the same project; re-pick the reference from the `${{` dropdown; check it with the eye icon |
| `/health` all ok, but `/documents`, `/conversations`, `/chat` return 500 | tables missing | look for `schema init failed` in the logs, fix the cause, redeploy |
| `/chat` always says "I couldn't find this in the documents." | no documents ingested yet, or the Pinecone index is shared with local | §6; §3 (separate index) |
| Pushed, but no new deployment | the commit isn't on `main` (pushed a branch only, or a rejected non-fast-forward push) | merge into `main`, §5 |
| `psql: could not translate host name "postgres.railway.internal"` | that host only exists inside Railway | use `DATABASE_PUBLIC_URL`, §4 |
| CLI shows a different project, or `--service` not found | logged into another Railway account, or linked to another project | `railway whoami`, `railway status`; `railway logout && railway login`; `railway link` |
| Vercel: header dots red, every API call fails | `API_URL` wasn't set when the UI was built, so `/api/*` still points at `http://localhost:8000` | set `API_URL` in Vercel, then redeploy |
| Vercel: changed `API_URL`, but the UI still calls the old API | `API_URL` is read at build time | redeploy |
| Vercel: build fails, or detects Python instead of Next.js | Root Directory isn't `web` | set Root Directory to `web` in the project settings, redeploy |

## Before sharing the URL

- **There's no authentication.** Anyone with the URL can upload and delete
  documents and spend your Groq and Pinecone quota. Add an API-key check
  before giving the URL out widely. That goes for both URLs: the Vercel UI
  is public, and the Railway API stays directly reachable behind it.
- `/health` returns raw error messages, including internal hostnames —
  fine while learning, worth trimming for anything public.

## CLI cheat sheet

```bash
railway whoami                                            # logged-in account
railway status                                            # linked project, services, URLs
railway deployment list --service learning_rag_0          # recent deploys
railway logs --service learning_rag_0                     # app logs
railway variable list --service learning_rag_0            # variables (prints secrets!)
railway variable set --service learning_rag_0 KEY=value   # set a variable (redeploys)
railway redeploy --service learning_rag_0 --from-source   # deploy latest main
railway open                                              # project dashboard in the browser
```
