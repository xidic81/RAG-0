# RAG Chatbot — hands-on build

A document Q&A chatbot over a PDF corpus, with citations back to filename
and page. Built incrementally, one git commit per step — see
[GUIDE.md](GUIDE.md) for the walkthrough and [specs.md](specs.md) for the
full design spec this follows.

Each step is tagged (`step-0`, `step-1`, ...) so you can check out any
point in the build:

```
git log --oneline
git checkout step-3   # see the repo exactly as it was after step 3
```

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- PostgreSQL 16 running locally
- A [Groq API key](https://console.groq.com/keys) for the default hosted LLM
- [Ollama](https://ollama.com) is optional; set `USE_OLLAMA=true` to use it
- A free [Pinecone](https://app.pinecone.io) account and API key (Starter
  tier — no card required)

## Setup

```bash
uv sync

# One-time: create the Postgres role + database (needs sudo)
sudo -u postgres psql -c "CREATE ROLE rag WITH LOGIN PASSWORD 'rag';"
sudo -u postgres psql -c "CREATE DATABASE rag OWNER rag;"
psql "postgresql://rag:rag@localhost:5432/rag" -f sql/schema.sql

# Your own secrets — fill in PINECONE_API_KEY and GROQ_API_KEY
cp .env.example .env

# Sample PDF corpus (5 public-domain books from Project Gutenberg,
# standing in for the ~200-PDF corpus in specs.md)
uv run python scripts/fetch_sample_corpus.py
```

## Running things

Start the API from the repository root in one terminal:

```bash
uv run uvicorn rag.api:app --reload
```

Then start the browser UI in another terminal:

```bash
cd web && npm install && npm run dev   # http://localhost:3000 (needs uvicorn running too)
```

Open http://localhost:3000 to chat. The API also needs the Postgres,
Groq (unless `USE_OLLAMA=true`) and Pinecone setup above. See [GUIDE.md](GUIDE.md) for the
step-by-step build, corpus ingestion, and what to try at each stage.

## Deploying

The API runs on Railway and the web UI on Vercel. Deploy the API first —
the UI needs its public URL.

### API → Railway

See [DEPLOYMENT.md](DEPLOYMENT.md) for setup, variables, deploying changes,
loading documents, and troubleshooting.

### Web UI → Vercel

See [DEPLOYMENT.md](DEPLOYMENT.md#web-ui-on-vercel) for setup, the `API_URL`
variable, how requests reach the API, and troubleshooting.
