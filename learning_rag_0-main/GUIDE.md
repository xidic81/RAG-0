# Hands-on guide

This is [specs.md](specs.md) built one piece at a time. Each section below
is one git commit, tagged `step-N`. Read the section, then look at the
actual diff for that commit — the code is short enough to read in full:

```
git show step-2          # the whole commit: diff + message
git diff step-1 step-2    # just what changed between two steps
```

The point of building it this way: a naive RAG system you fully understand
teaches you more than a sophisticated one you copy-pasted. Don't skip ahead
to the exercises in specs.md §9 until steps 0–8 all work end to end.

---

## Step 0 — scaffold

**Commit:** project skeleton, Postgres schema, sample PDF corpus.

Nothing about RAG yet — just the plumbing so later steps have something to
run against:

- `pyproject.toml` — managed with `uv`, dependencies added incrementally as
  each step needs them (watch the diffs — you'll see exactly which package
  enabled which feature).
- `sql/schema.sql` — the four tables from specs.md §3.1, copied verbatim.
  `documents`/`chunks` hold the corpus, `conversations`/`messages` hold chat
  history. Note there's no vector column here — Postgres never stores
  embeddings, only text and metadata.
- `.env.example` — the config every later step reads: Postgres DSN,
  Pinecone key, and LLM provider settings. Groq is the default; set
  `USE_OLLAMA=true` to use Ollama. Copy to `.env` and fill in your keys.
- `scripts/fetch_sample_corpus.py` — downloads 5 public-domain books from
  Project Gutenberg and paginates them into PDFs under `data/pdfs/`. This
  stands in for the 200-PDF corpus in specs.md — small enough to iterate on
  fast, but real enough (335 real pages) that retrieval can actually fail
  in interesting ways.

**Run it:**

```bash
uv sync
uv run python scripts/fetch_sample_corpus.py
ls data/pdfs
```

You should see 5 PDFs, ~30–130 pages each.

---

## Step 1 — load one PDF, look at the chunks

**Commit:** `rag/ingest.py` with `load_and_split()`.

Before writing anything to a database, look at what the loader and
splitter actually produce. This is the step people skip, and then spend
an hour later debugging bad citations that were actually bad chunking.

`load_and_split()` does exactly two things (specs.md §4):

1. `PyMuPDFLoader` loads the PDF as one `Document` per page — this is
   where `metadata["page"]` comes from, straight from the PDF's own page
   numbers, zero-indexed.
2. `RecursiveCharacterTextSplitter` cuts those pages into ~1000-character
   chunks with 200 characters of overlap, and copies each parent page's
   metadata onto every chunk it produces.

That metadata copy is the entire citation mechanism. There's no separate
"figure out what page this text came from" step anywhere in this project
— it's just inherited and carried along.

**Run it:**

```bash
uv run python -m rag.ingest data/pdfs/jekyll-and-hyde.pdf
```

You should see chunk previews with `page=` and `chars=` on each — confirm
the text reads cleanly (no garbled characters, no page-header/footer junk)
and the page numbers climb as you'd expect. If this looks wrong, nothing
downstream will work — fix it here first.

(You'll see a `DeprecationWarning` about `langchain-community` — that's
the exact package specs.md §2.1 calls for; safe to ignore for this
project's purposes.)

---

## Step 2 — ingest one PDF into Postgres and Pinecone

**Commit:** `rag/config.py`, `rag/db.py`, `rag/pinecone_store.py`, and
`ingest_document()` added to `rag/ingest.py`.

Three new pieces, each doing one job:

- `rag/config.py` — every setting (Postgres DSN, Pinecone key, Groq and
  Ollama settings) read from `.env` in one place. Every other module imports
  `settings` from here; nothing reads `os.environ` directly anywhere else.
- `rag/db.py` — thin wrappers around the schema from Step 0. Postgres is
  the system of record for chunk text; nothing here talks to Pinecone.
- `rag/pinecone_store.py` — vectors only, keyed by `chunk.id`. With
  Pinecone's integrated inference you upsert raw text and it embeds
  server-side, so there's no embedding client to write.

`ingest_document()` ties them together: compute the file's sha256, skip if
already ingested (specs.md §4.2 idempotency), otherwise write chunks to
Postgres and upsert the matching vectors to Pinecone, both keyed by the
same id. The document's `status` moves `pending -> processing -> ready`
(or `failed`, with the error saved) as it goes — that's what
`GET /documents` will report once the API exists in Step 7.

**Two bugs worth knowing about, because you'll hit their shape again:**

1. **`Pinecone(api_key=...)` validates the key eagerly, at construction
   time.** Building the client as a module-level global broke *importing*
   `rag.pinecone_store` entirely whenever `PINECONE_API_KEY` was unset —
   which would have taken down every other route in the Step 7 API too,
  including the Postgres and selected-LLM health checks that have nothing to
   do with Pinecone. Fix: build the client lazily, on first real use
   (see `pinecone_store._client()`).
2. **`upsert_records` sends your whole list as one HTTP request, with no
   client-side batching**, and Pinecone's integrated-embedding endpoint
   caps how many records one request can carry. A single one of our
   books can produce 600+ chunks. `upsert_chunks()` batches in groups of
   90 to stay safely under that.

**Run it** (needs Postgres running and `PINECONE_API_KEY` set in `.env`):

```bash
# one-time: apply the schema (see README for creating the role/database first)
psql "$POSTGRES_DSN" -f sql/schema.sql

uv run python -m rag.ingest run data/pdfs/jekyll-and-hyde.pdf
# ingested jekyll-and-hyde.pdf: 163 chunks (doc <uuid>)

uv run python -m rag.ingest run data/pdfs/jekyll-and-hyde.pdf   # run again
# skip jekyll-and-hyde.pdf: already ingested (doc <uuid>)        <- idempotency
```

---

## Step 3 — retrieve and print, no LLM yet

**Commit:** `rag/retrieve.py`.

specs.md §5, and it really is one call:

```
query --> Pinecone dense search (top 5) --> LLM
```

`retrieve()` searches Pinecone for the top-k chunk ids + scores, then
fetches their text from Postgres in one query. No LLM involved yet on
purpose — retrieval is the thing you'll debug the most in this project,
and it's much easier to debug with the LLM out of the loop.

**A third bug**, also only found by running it: the Pinecone SDK's `Hit`
objects don't support `hit["_id"]` the way specs.md §5's example snippet
shows — that raises `KeyError`. The installed SDK exposes it as the
`.id` attribute instead (`.score` likewise, not `["_score"]`). Worth
remembering generally: treat a spec's illustrative snippets as intent,
not as guaranteed-correct code against whatever SDK version you actually
have installed.

**Run it:**

```bash
uv run python -m rag.retrieve "What is Mr. Utterson's profession?"
```

On our sample corpus this is a good first look at specs.md §5.2's
predicted failure modes: the page that states outright "Mr. Utterson the
lawyer was a man of..." often *isn't* in the top 5 — dense search finds
chunks that are topically similar (Utterson doing lawyer-ish things)
without necessarily finding the one sentence that states his job. That's
not a bug in this code; it's the exact reason specs.md §9 exercises
(reranking, hybrid search) exist.

---

## Step 4 — add the LLM call: a working RAG system

**Commit:** `rag/generate.py`, `rag/prompts/system_prompt.txt`,
`rag/chat.py`.

Three pieces:

- `rag/prompts/system_prompt.txt` — the prompt from specs.md §6.1, in its
  own file (not inlined in Python) because you'll edit it constantly.
- `rag/generate.py` — `generate(messages) -> str`, the *only* function
  that talks to the selected LLM provider. Set `USE_OLLAMA=true` for
  Ollama; otherwise generation uses Groq.
- `rag/chat.py` — `ask(question)`, the full loop: retrieve, refuse early
  if the top score is too low (specs.md §6.2), otherwise generate. This
  is the one function the Step 7 API will just wrap.

The refusal threshold isn't guessed — `SCORE_THRESHOLD` is set from real
numbers, measured with the eval harness in Step 6 once the whole corpus
is ingested (that section shows exactly how). It starts as a rough
placeholder here because you can't calibrate it against a corpus that's
only got one book in it yet.

**Run it:**

```bash
uv run python -m rag.chat "What is Mr. Utterson's profession?"
```

Groq is used by default and requires `GROQ_API_KEY` in `.env`. To use
Ollama instead, set `USE_OLLAMA=true` and configure `OLLAMA_HOST` and
`OLLAMA_MODEL`.

---

## Step 5 — ingest the full corpus

**Commit:** `scripts/ingest_all.py`, and the extraction cache
(`_load_pages()`) added to `rag/ingest.py`.

`scripts/ingest_all.py` just loops `ingest_document()` over every PDF in
`data/pdfs/` -- stands in for "ingest all 200 PDFs" with our 5-book
sample corpus. One bad file shouldn't sink the whole batch, so failures
are caught per-file and reported at the end (also visible per-document
via `documents.status`/`error` in Postgres).

The other change, specs.md §4.1: `_load_pages()` now caches
`PyMuPDFLoader`'s output to disk, keyed by file hash. You'll re-run
chunking many times while tuning `chunk_size` (Exercise 1) -- re-parsing
every page of the corpus on every attempt makes that loop unbearable, and
this sidesteps it entirely: the cache lives outside Postgres/Pinecone, so
it doesn't interact with ingest's idempotency check at all, it just makes
re-running `load_and_split()` on an already-seen file nearly free.

**Run it:**

```bash
uv run python scripts/ingest_all.py
```

(If you get `ModuleNotFoundError: No module named 'rag'` running a
script directly like this, it's because `python scripts/foo.py` puts
`scripts/` on `sys.path`, not the project root -- `python -m rag.ingest`
avoided this because `-m` adds the *current directory*. The scripts here
add the project root to `sys.path` themselves to sidestep it.)

Tested live: ingested all 5 books (1,672 chunks total), with the
already-ingested one correctly skipped. Along the way, testing deletion
turned up two things worth knowing if you go looking at Pinecone data
directly while debugging:

- **Pinecone writes and deletes are eventually consistent, not
  immediate.** A vector can still `fetch()` for several seconds after a
  successful delete call, and `describe_index_stats()` lags even further
  behind. Don't conclude a delete failed just because a query run
  immediately after still finds the old data -- wait a few seconds and
  check again.
- Because of that, **manually poking at Pinecone data while debugging is
  easy to get wrong** -- reusing the same document for a "does this
  work" check and a "did that actually delete it" check in the same
  script can leave Postgres and Pinecone out of sync with each other,
  since ingest's idempotency check only looks at Postgres. If retrieval
  ever looks emptier than it should for a document Postgres reports as
  `ready`, re-ingesting is the fix.

---

## Step 6 — evaluation harness + baseline

**Commit:** `eval/testset.csv`, `eval/run_eval.py`, and
`SCORE_THRESHOLD` recalibrated in `rag/chat.py`.

specs.md §8: do this before the exercises, or every change you make
after this point is just guessing whether it helped.

`eval/testset.csv` is 20 question/answer pairs plus 5 the corpus can't
answer, hand-built by actually reading the generated PDFs page by page
(not from memory of these books' original editions -- our pagination is
custom, so "page 12" only means something if it's *our* page 12). It
covers the three categories specs.md §8.1 asks for: `factual`,
`identifier` (exact names/addresses/titles -- the things dense search
struggles with per §5.2), and `multi-doc` (needs chunks from two
different books to answer).

`eval/run_eval.py recall` computes **recall@5**: for each question, was
a chunk from the expected (filename, page) among the top 5 retrieved?
No LLM involved, runs in seconds -- specs.md §8.2 calls this "the metric
you'll use for almost every experiment," and after running it you'll see
why: it's fast enough to run after every single change.

`eval/run_eval.py answers` runs the full `rag.chat.ask()` pipeline and
writes `eval/results.csv` with a blank `correct(y/n)` column for grading
by hand -- specs.md §8.2's "answer accuracy," slower but the thing that
actually matters.

**Run it:**

```bash
uv run python -m eval.run_eval recall
```

**Actual result on our sample corpus:**

```
factual      10/11  (91%)
identifier   5/6   (83%)
multi-doc    0/3   (0%)
overall      15/20 (75%)
```

75% lands right in specs.md §8.2's predicted 0.6–0.75 baseline range for
a clean English corpus -- a good sign the pipeline is behaving as
designed, not a red flag. The `multi-doc` 0/3 is expected and
instructive, not a bug: a single dense-vector query against 5 unrelated
books has no real mechanism for surfacing chunks from *two* of them at
once in one top-5. That's precisely the gap query rewriting and
multi-hop techniques exist to close -- out of scope for v1, but now you
have a number to compare against if you ever build one.

The script also prints the top-1 score for each of the 5 unanswerable
questions, which is exactly the specs.md §6.2 calibration data: our 5
topped out at 0.342, while none of the 20 answerable questions scored
below 0.388. `SCORE_THRESHOLD` in `rag/chat.py` is set to 0.36 --
comfortably in that gap, measured rather than guessed. If you change the
corpus, re-run this and recheck the gap still holds.

---

## Step 7 — wrap it in FastAPI

**Commit:** `rag/api.py`.

Every endpoint from specs.md §7 is a thin HTTP layer over functions the
earlier steps already built and tested from the command line --
`/chat` *is* `rag.chat.ask()`, `POST /documents` *is*
`rag.ingest.ingest_document()`. The API's only new job is HTTP plumbing
plus persisting conversation history to the `conversations`/`messages`
tables, which no earlier step needed.

`POST /documents` saves the upload, then runs `ingest_document()` as a
FastAPI `BackgroundTasks` job so the HTTP response doesn't block on
however long ingestion takes -- poll `GET /documents` to watch `status`
move `pending -> processing -> ready`.

`GET /health` checks Postgres, Pinecone, and the selected LLM provider independently and
reports all three regardless of which ones are down -- this only works
correctly because of the lazy-Pinecone-client fix from Step 2. Before
that fix, an unset `PINECONE_API_KEY` would have crashed the *whole app*
on import, and you'd never even see that Postgres and the selected LLM provider were fine.

**Run it:**

```bash
uv run uvicorn rag.api:app --reload
```

```bash
curl -X POST localhost:8000/documents -F file=@data/pdfs/frankenstein.pdf
curl localhost:8000/documents
curl -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message": "What is Mr. Utterson'"'"'s profession?"}'
curl localhost:8000/health
```

Tested live end to end, including the upload path: a freshly uploaded
one-page test PDF went `queued -> ready` and became correctly
retrievable a few seconds later (the same Pinecone write-latency as
Step 5's delete-latency finding -- give a fresh upload a moment before
querying it). Its score for a direct question landed at 0.355, just
under our 0.36 threshold -- an unplanned but accurate demonstration of
specs.md §5.2's "exact identifiers embed poorly," since the test content
was a single made-up code word.

**A blocking response is far easier to debug than streaming** (specs.md
§7.1) -- you can `curl` it and read the output directly. SSE streaming
is Exercise 7, once everything above it already works.

---

## Step 8 — a minimal UI

**Commit:** the Next.js app under `web/`.

The UI puts a usable browser surface on the API: ask questions in a chat,
see answers and their filename/page citations, start a new conversation,
check the Postgres/Pinecone/LLM health status, and upload or delete
PDFs from the Documents page. The API still owns retrieval, generation,
ingestion, and persistence; the web app is a client for those endpoints.

The browser calls `/api/...`, and `web/next.config.ts` rewrites those
requests to the FastAPI server at `localhost:8000`. This proxy keeps the
browser's requests same-origin, so the API does not need CORS configuration
for this local UI. It also gives the frontend one stable API path rather
than exposing the backend host in browser code.

Chat messages are persisted by `POST /chat`, but the page keeps the
displayed messages in client state. There is no
`GET /conversations/{id}/messages` endpoint yet, so refreshing the page
loses the visible transcript even though the conversation remains in the
database. The smallest next backend step is to add that GET endpoint to
return a conversation's messages in order (including saved citations),
then have the UI load them when opening a conversation. Until then, a
refresh starts a blank chat; reloading past conversations is deliberately
not part of this step.

**Run it:**

Start FastAPI from the repository root in one terminal (with the Step 7
services configured and running):

```bash
uv run uvicorn rag.api:app --reload
```

In another terminal, start the web app:

```bash
cd web && npm install && npm run dev
```

Open <http://localhost:3000>. The health indicator should show whether
Postgres, Pinecone, and the selected LLM provider are reachable. To get answers from the
sample corpus, ingest it first if you have not already:

```bash
uv run python scripts/ingest_all.py
```

**Try it:** ask a question answered by one of the ingested PDFs and check
the citation; click **New chat** and ask another question; visit
**Documents** to upload a PDF and watch its status update, then delete it.
Refresh the chat page once to see the current history limitation: the
conversation is saved by the API, but the UI has no endpoint to reload it.

---

## What's next

Steps 0–8 take you from the scaffold to a working, measured RAG system
with a minimal browser UI. Don't move on to specs.md §9's exercises until `recall@5` and
the eval harness above are both running cleanly for you locally --
they're what tells you whether each exercise actually helped.

From here, specs.md §9 is the same habit repeated: change one thing,
re-run `eval.run_eval recall`, write down the number, keep the change
only if it helped. Given what recall@5 already showed on this corpus,
Exercise 6 (reranking) and Exercise 2 (hybrid search, for the
`identifier`-category misses) are the two most likely to move the
needle first.
