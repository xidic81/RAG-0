-- Schema from specs.md §3.1, made idempotent (IF NOT EXISTS) so it's safe
-- to re-run. The API runs it on every startup (rag.db.init_schema), so a
-- fresh database -- e.g. a new Railway Postgres -- needs no manual step.
-- Running it by hand still works:
--   psql "$POSTGRES_DSN" -f sql/schema.sql
--
-- IDs are generated in Python (uuid4), not by the database: the same chunk
-- id has to be known *before* the row is written, so it can also be used as
-- the Pinecone vector key in the same ingest step.

CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_hash   TEXT NOT NULL UNIQUE,   -- sha256, for idempotent re-ingest
    page_count  INT,
    status      TEXT NOT NULL,          -- pending|processing|ready|failed
    error       TEXT,
    ingested_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id      UUID PRIMARY KEY,
    doc_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page    INT,
    text    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_doc_id_idx ON chunks (doc_id);

CREATE TABLE IF NOT EXISTS conversations (
    id         UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,      -- user | assistant
    content         TEXT NOT NULL,
    citations       JSONB,              -- [{filename, page}]
    retrieval_debug JSONB,              -- retrieved chunk ids + scores
    created_at      TIMESTAMPTZ DEFAULT now()
);
