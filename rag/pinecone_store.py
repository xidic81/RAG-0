"""Pinecone: vectors only, keyed by chunk.id. specs.md §3.2.

Chunk text is deliberately not duplicated into Pinecone metadata -- text
lives in Postgres, Pinecone holds the embedding plus just enough metadata
(doc_id, page) to filter and delete by document. With integrated
inference, we upsert raw text and Pinecone embeds it server-side: no
embedding client to write here at all.
"""

from __future__ import annotations

from pinecone import IndexEmbed, Pinecone

from rag.config import settings

_pc: Pinecone | None = None


def _client() -> Pinecone:
    """Built on first use, not on import -- so the rest of the app still
    imports and runs (health checks included) before PINECONE_API_KEY is
    set."""
    global _pc
    if _pc is None:
        _pc = Pinecone(api_key=settings.pinecone_api_key)
    return _pc


def ensure_index() -> None:
    """Create the index if it doesn't exist yet. Safe to call every run."""
    pc = _client()
    if settings.pinecone_index in pc.list_indexes().names():
        return
    pc.create_index_for_model(
        name=settings.pinecone_index,
        cloud="aws",
        region="us-east-1",
        embed=IndexEmbed(
            model="llama-text-embed-v2",
            field_map={"text": "text"},
            metric="cosine",
        ),
    )


def _index():
    return _client().Index(settings.pinecone_index)


# upsert_records embeds server-side within the request itself, so unlike a
# plain vector upsert it isn't a cheap operation -- Pinecone caps how many
# records one call can carry. The SDK sends whatever list you give it as a
# single HTTP request with no client-side batching, so a whole book's
# worth of chunks in one call risks hitting that cap. Batch defensively.
_UPSERT_BATCH_SIZE = 90


def upsert_chunks(records: list[dict], namespace: str = "default") -> None:
    """records: [{"_id": chunk_id, "text": chunk_text, "doc_id": ..., "page": ...}, ...]"""
    index = _index()
    for i in range(0, len(records), _UPSERT_BATCH_SIZE):
        index.upsert_records(records=records[i : i + _UPSERT_BATCH_SIZE], namespace=namespace)


def search(query_text: str, top_k: int = 5, namespace: str = "default") -> list[dict]:
    """Returns [{"chunk_id": ..., "score": ...}, ...] ranked best first."""
    results = _index().search(
        namespace=namespace,
        query={"inputs": {"text": query_text}, "top_k": top_k},
    )
    # specs.md §5 shows hit["_id"] (the raw wire field name); the installed
    # SDK's Hit object exposes that as the .id attribute instead.
    return [{"chunk_id": hit.id, "score": hit.score} for hit in results["result"]["hits"]]


def delete_by_doc(doc_id: str, namespace: str = "default") -> None:
    _index().delete(filter={"doc_id": doc_id}, namespace=namespace)
