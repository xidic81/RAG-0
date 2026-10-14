"""Postgres access. This is the system of record for chunk text and
conversations -- Pinecone stores vectors only. specs.md §3.1.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from rag.config import settings

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.postgres_dsn, row_factory=dict_row, autocommit=True)


def init_schema(conn: psycopg.Connection) -> None:
    """Create any missing tables. schema.sql is all IF NOT EXISTS, so this
    is a no-op on a database that's already set up -- safe to run on every
    API startup."""
    conn.execute(_SCHEMA_PATH.read_text())


def find_document_by_hash(conn: psycopg.Connection, file_hash: str) -> dict | None:
    return conn.execute(
        "SELECT id, status FROM documents WHERE file_hash = %s",
        (file_hash,),
    ).fetchone()


def insert_document(
    conn: psycopg.Connection,
    doc_id: str,
    filename: str,
    file_hash: str,
    status: str,
    page_count: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO documents (id, filename, file_hash, page_count, status)
        VALUES (%s::uuid, %s, %s, %s, %s)
        """,
        (doc_id, filename, file_hash, page_count, status),
    )


def update_document_status(conn: psycopg.Connection, doc_id: str, status: str, error: str | None = None) -> None:
    conn.execute(
        "UPDATE documents SET status = %s, error = %s WHERE id = %s::uuid",
        (status, error, doc_id),
    )


def mark_processing(conn: psycopg.Connection, doc_id: str, page_count: int) -> None:
    conn.execute(
        "UPDATE documents SET status = 'processing', page_count = %s WHERE id = %s::uuid",
        (page_count, doc_id),
    )


def delete_document(conn: psycopg.Connection, doc_id: str) -> None:
    """Cascades to chunks (ON DELETE CASCADE). Caller is responsible for
    also deleting the matching vectors from Pinecone -- the two stores are
    linked only by chunk.id, there's no foreign key across systems."""
    conn.execute("DELETE FROM documents WHERE id = %s::uuid", (doc_id,))


def insert_chunks(conn: psycopg.Connection, rows: list[tuple[str, str, int, str]]) -> None:
    """rows: [(chunk_id, doc_id, page, text), ...]"""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO chunks (id, doc_id, page, text) VALUES (%s::uuid, %s::uuid, %s, %s)",
            rows,
        )


def fetch_chunks(conn: psycopg.Connection, chunk_ids: list[str]) -> dict[str, dict]:
    """Returns {chunk_id: {"filename": ..., "page": ..., "text": ...}}."""
    rows = conn.execute(
        """
        SELECT chunks.id, chunks.page, chunks.text, documents.filename
        FROM chunks
        JOIN documents ON documents.id = chunks.doc_id
        WHERE chunks.id = ANY(%s::uuid[])
        """,
        (chunk_ids,),
    ).fetchall()
    return {str(row["id"]): row for row in rows}


def list_documents(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        "SELECT id, filename, page_count, status, error, ingested_at FROM documents ORDER BY ingested_at DESC"
    ).fetchall()


def create_conversation(conn: psycopg.Connection, conversation_id: str) -> None:
    conn.execute("INSERT INTO conversations (id) VALUES (%s::uuid)", (conversation_id,))


def find_conversation(conn: psycopg.Connection, conversation_id: str) -> dict | None:
    return conn.execute(
        "SELECT id FROM conversations WHERE id = %s::uuid",
        (conversation_id,),
    ).fetchone()


def insert_message(
    conn: psycopg.Connection,
    message_id: str,
    conversation_id: str,
    role: str,
    content: str,
    citations: list | None = None,
    retrieval_debug: list | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO messages (id, conversation_id, role, content, citations, retrieval_debug)
        VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s)
        """,
        (message_id, conversation_id, role, content, Json(citations), Json(retrieval_debug)),
    )
