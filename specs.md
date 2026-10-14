# RAG Chatbot — Learning Project Specification

**Project:** Document question-answering system over a 200+ PDF corpus
**Purpose:** Hands-on introduction to RAG
**Version:** 2.0 — simplified for learning
**Date:** August 2026

---

## 0. How to use this document

Sections 1–8 describe **v1: the simplest RAG system that works.** Build that first, end to end, before adding anything.

Section 9 contains **staged exercises** — the techniques that were in the original design, reintroduced one at a time. Each has a measurable before/after. Doing them in order is the point: you learn *why* reranking exists by first seeing retrieval fail without it.

Resist the urge to build the full pipeline immediately. A working naive system that answers 60% of questions teaches more than a sophisticated one you can't debug.

---

## 1. Overview

A RAG chatbot that answers questions from a PDF library, with citations back to filename and page.

### 1.1 Scale

| Metric | Estimate |
|---|---|
| Documents | ~200 PDFs |
| Pages | ~6,000 |
| Raw tokens | ~3,000,000 |
| Chunks | ~4,000 |
| Vector storage | < 30 MB |

Small enough to fit entirely inside free tiers.

### 1.2 PDF characteristics (confirmed)

1. Digital text — no OCR needed
2. English only
3. Charts and images are ignored

This simplifies things considerably. One loader, one embedding model, no OCR path.

---

## 2. Architecture

```
                    ┌─────────────────┐
   PDFs  ──────────▶│  Ingestion      │
                    │  (offline)      │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
      ┌───────────────┐            ┌────────────────┐
      │   Postgres    │            │    Pinecone    │
      │  docs/chunks  │◀──────────▶│    vectors     │
      │  chat history │  chunk_id  │                │
      └───────────────┘            └────────────────┘
              ▲                             ▲
              └──────────────┬──────────────┘
                             │
                    ┌────────┴────────┐
   User  ◀─────────▶│   FastAPI       │◀──────▶ LLM
                    │   /chat         │    (Groq or Ollama)
                    └─────────────────┘
```

Postgres is the system of record for chunk text and conversations. Pinecone stores only vectors keyed by `chunk.id`. Chunk text is deliberately not duplicated into Pinecone metadata — keeping the index small and making text edits cheap.

### 2.1 Component choices

| Layer | Choice | Why |
|---|---|---|
| PDF loading | `PyMuPDFLoader` | Only loader needed for digital text |
| Splitting | `RecursiveCharacterTextSplitter` | One splitter, one size |
| Embeddings | Pinecone hosted `llama-text-embed-v2` | Free tier, English, no local model to manage |
| Vector store | Pinecone Starter | Free |
| LLM | Groq by default; optional Ollama | Hosted API key by default; local model when `USE_OLLAMA=true` |
| Metadata DB | PostgreSQL 16 | |
| API | FastAPI | |

**Keep the LLM behind one function** — `generate(messages) -> str`. Select Groq (default) or Ollama with `USE_OLLAMA=true`.

---

## 3. Data model

### 3.1 PostgreSQL schema

```sql
CREATE TABLE documents (
    id          UUID PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_hash   TEXT NOT NULL UNIQUE,   -- sha256, for idempotent re-ingest
    page_count  INT,
    status      TEXT NOT NULL,          -- pending|processing|ready|failed
    error       TEXT,
    ingested_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chunks (
    id      UUID PRIMARY KEY,
    doc_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page    INT,
    text    TEXT NOT NULL
);
CREATE INDEX ON chunks (doc_id);

CREATE TABLE conversations (
    id         UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,      -- user | assistant
    content         TEXT NOT NULL,
    citations       JSONB,              -- [{filename, page}]
    retrieval_debug JSONB,              -- retrieved chunk ids + scores
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

One flat `chunks` table — no parent/child hierarchy in v1.

**Keep `retrieval_debug` even in v1.** When the bot gives a wrong answer, the first question is always "did retrieval find the right chunk, or did the LLM misread a correct one?" Without the recorded scores you cannot tell, and those are two completely different bugs.

### 3.2 Pinecone index

| Setting | Value |
|---|---|
| Type | Serverless, AWS `us-east-1` |
| Embedding model | `llama-text-embed-v2` via integrated inference |
| Metric | cosine |
| Metadata | `doc_id`, `page` |

With integrated inference you upsert raw text and Pinecone embeds it server-side — no embedding client to write.

---

## 4. Ingestion pipeline

Four steps: load → split → store → embed.

```python
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

pages = PyMuPDFLoader(path).load()          # one Document per page

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)
chunks = splitter.split_documents(pages)     # page metadata is inherited
```

Each chunk arrives carrying `metadata["source"]` and `metadata["page"]` automatically. **That inheritance is your entire citation layer** — no manual page tracking needed.

Write chunks to Postgres, then upsert to Pinecone keyed by `chunk.id` with `doc_id` and `page` as metadata.

### 4.1 Cache the extraction output

Serialize the loader output to disk keyed by `file_hash`. You will re-run chunking many times while experimenting with `chunk_size`; re-parsing 6,000 pages each time makes that loop unbearable, and re-embedding repeatedly will burn through the 5M/month free token allowance.

### 4.2 Idempotency

Ingest is keyed on `file_hash`. An unchanged file is a no-op. A changed file deletes its old chunks and vectors first. Deleting a document cascades in Postgres and issues a Pinecone delete filtered on `doc_id`.

---

## 5. Retrieval — v1

```
query ──▶ Pinecone dense search (top 5) ──▶ LLM
```

That's it. One call.

```python
results = index.search(
    namespace="default",
    query={"inputs": {"text": user_question}, "top_k": 5},
)
chunk_ids = [hit["_id"] for hit in results["result"]["hits"]]
chunks = fetch_chunks_from_postgres(chunk_ids)
```

### 5.1 Why top 5

Two forces pull in opposite directions. More chunks means a better chance the answer is somewhere in the context. Fewer chunks means the model is less likely to latch onto an irrelevant passage — small models degrade noticeably when the right answer is buried among distractors.

Without a reranker, dense search alone is noisy, so you need a few extra shots on goal. Five is a reasonable starting point. **Try 3 and 10 and observe what breaks** — this is one of the most instructive experiments in the whole project.

### 5.2 What this will get wrong

Predicting the failures in advance makes them much more legible when they appear:

- **Exact identifiers.** Product codes, invoice numbers, and unusual proper nouns embed poorly. Ask for "part number XR-4471" and dense search often returns semantically similar but wrong passages. → Exercise 2.
- **Chunk boundaries.** When an answer straddles two chunks, you may retrieve the half that doesn't contain it. → Exercises 1 and 4.
- **Ambiguous context.** A chunk that says "the notice period is 90 days" without naming the contract is useless when 30 documents contain a notice period. → Exercise 3.
- **Follow-up questions.** "What about the other one?" embeds to nothing meaningful. → Exercise 5.

Note which of these actually bite your corpus. That determines which exercise is worth doing first.

---

## 6. Generation

### 6.1 Prompt

```
You are a document assistant. Answer using ONLY the context below.

Rules:
- Cite the source as [filename, page N] after each claim.
- If the context does not contain the answer, say so plainly.
- Do not use outside knowledge.

Context:
{numbered chunks with filename and page}

Question: {question}
```

Keep the system prompt in a separate file, not inline in the code. You will edit it constantly.

### 6.2 Refusal

If the top Pinecone score falls below a threshold, return "I couldn't find this in the documents" without calling the LLM at all.

Calibrate the threshold by hand: run 10 questions you *know* the corpus can't answer, look at the top scores they produce, and set the cutoff below that band. Cosine scores are not calibrated probabilities and the right threshold is corpus-specific, so this must be measured rather than guessed.

---

## 7. API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/documents` | Upload PDF, ingest async |
| `GET` | `/documents` | List with status |
| `DELETE` | `/documents/{id}` | Remove document, chunks, vectors |
| `POST` | `/conversations` | Create conversation |
| `POST` | `/chat` | Ask a question |
| `GET` | `/health` | Postgres / Pinecone / selected LLM provider reachability |

### 7.1 `POST /chat`

**Request**

```json
{
  "conversation_id": "uuid | null",
  "message": "What is the termination notice period in the Acme agreement?"
}
```

**Response** — plain JSON in v1

```json
{
  "conversation_id": "uuid",
  "message_id": "uuid",
  "answer": "The agreement requires 90 days written notice [acme-2024.pdf, page 12].",
  "citations": [{"filename": "acme-2024.pdf", "page": 12}]
}
```

SSE streaming is Exercise 7. A blocking response is far easier to debug — you can `curl` it and read the output.

---

## 8. Evaluation

Do this before any of the exercises. Without it there is no way to tell whether a change helped, and every exercise below becomes guesswork.

### 8.1 Build a test set

20 question/answer pairs, each annotated with the document and page containing the answer. Plus 5 questions the corpus cannot answer. A CSV is fine.

Cover: simple factual lookup, exact-identifier lookup, and questions whose answer requires two documents.

### 8.2 Measure two things

**Recall@k** — was the correct chunk among the retrieved ones? This tests retrieval alone and needs no LLM, so it runs in seconds. It is the metric you will use for almost every experiment.

**Answer accuracy** — did the final answer say the right thing? Graded by hand. Slower, but it's what actually matters.

Recording both separates the two failure modes: if recall is high but accuracy is low, the retrieval is fine and the prompt or model is at fault. If recall is low, nothing downstream can save you.

A rough baseline for v1 on a clean English corpus is recall@5 in the 0.6–0.75 range. If you're far below that, something is wrong with chunking or ingestion — investigate before starting the exercises.

---

## 9. Exercises

Each exercise adds one technique. Run the evaluation before and after, and write down both numbers. The habit of measuring one change at a time is more valuable than any individual technique here.

### Exercise 1 — Tune chunk size

No new code. Try 500 / 1000 / 2000 characters and overlaps of 0 / 100 / 200. Measure recall@5 for each.

*Expect:* a clear optimum, and a surprisingly large spread between best and worst. Often the single cheapest quality gain available.

### Exercise 2 — Add keyword search (hybrid retrieval)

Add BM25 over the chunk text with `rank_bm25`, retrieve 25 from each method, and fuse with reciprocal rank fusion:

```python
def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)
```

RRF needs no score normalization and no tuning, which is why it's the standard choice.

*Expect:* large gains specifically on exact-identifier questions, little change elsewhere. Write your test set so it can show this difference.

### Exercise 3 — Contextual headers

Before embedding, prefix each chunk with where it came from:

```
From "2024 Vendor Agreement — Acme Corp", page 12:
<chunk text>
```

Requires a full re-embed, so mind the free token allowance.

*Expect:* better disambiguation when many documents cover similar ground. This is why the extraction cache from §4.1 matters.

### Exercise 4 — Small-to-big retrieval

Embed small chunks (~300 tokens) for precise matching, but store a `parent_id` pointing to a larger ~1,200-token chunk. Search the small ones, send the parent to the LLM.

Requires adding `parent_id` and `is_parent` to the `chunks` table.

*Expect:* recall@k roughly unchanged, answer accuracy improved — the model has the surrounding context it needs to actually compose an answer.

### Exercise 5 — Query rewriting

Use the LLM to rewrite follow-up questions into standalone ones before retrieval, using the conversation history.

*Expect:* multi-turn conversations become usable. Test by asking three related questions in sequence.

### Exercise 6 — Reranking

Add a cross-encoder (`bge-reranker-v2-m3`, ~600 MB, CPU is fine). Retrieve 25, rerank, keep top 3.

*Expect:* typically the largest single jump in the whole pipeline. With reranking in place, revisit the top-k question from §5.1 — the right k is usually smaller once the ordering is trustworthy.

### Exercise 7 — Streaming

Convert `/chat` to SSE. Emit citations first, then answer tokens, so a UI can render source cards while the answer arrives.

### Exercise 8 — Deduplication

Overlapping chunks from the same page frequently both survive retrieval, wasting slots on near-identical text. Drop candidates whose similarity to an already-selected chunk exceeds 0.95.

*Expect:* small gains; matters more once overlap is large or k is small.

---

## 10. Costs

The database and vector store can fit within their free tiers; Groq usage depends on its current API limits and pricing.

| Item | Cost |
|---|---|
| Embedding ~3M tokens | Free (Pinecone Starter: 5M tokens/month) |
| Vector storage ~4k vectors | Free (2 GB / ~100k vector cap) |
| LLM inference | Groq API usage or local Ollama, selected by `USE_OLLAMA` |
| Postgres | Free (local Docker) |

The one real constraint: re-embedding the whole corpus more than once per month exceeds the free token allowance. This is why extraction is cached and why Exercise 3 (which forces a re-embed) is worth batching with any other chunking change you want to test.

Also note: Starter indexes pause after 3 weeks of inactivity, and Starter is AWS `us-east-1` only.

---

## 11. Suggested build order

1. Load one PDF, print the chunks. Confirm the text and page numbers look right.
2. Ingest that one PDF end to end, into Postgres and Pinecone.
3. Query it from a script. No API, no chat — just retrieve and print.
4. Add the LLM call. Now you have a working RAG system.
5. Ingest all 200 PDFs.
6. Build the evaluation set and get a baseline number.
7. Wrap it in FastAPI.
8. Start the exercises.

Steps 1–4 should take a day. That working end-to-end version, however rough, is what makes everything after it comprehensible.