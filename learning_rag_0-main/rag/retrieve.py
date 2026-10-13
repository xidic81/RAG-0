"""Retrieval: dense search in Pinecone, chunk text fetched from Postgres.
specs.md §5. One call, nothing fancier yet:

    query --> Pinecone dense search (top 5) --> LLM
"""

from __future__ import annotations

import sys

from rag import db, pinecone_store

TOP_K = 5


def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """Returns chunks ranked best first:
    [{"chunk_id", "score", "filename", "page", "text"}, ...]
    """
    hits = pinecone_store.search(query, top_k=top_k)
    chunk_ids = [hit["chunk_id"] for hit in hits]

    with db.connect() as conn:
        chunks_by_id = db.fetch_chunks(conn, chunk_ids)

    results = []
    for hit in hits:
        chunk = chunks_by_id.get(hit["chunk_id"])
        if chunk is None:
            continue  # vector exists but the row is gone -- shouldn't happen if ingest stays consistent
        results.append(
            {
                "chunk_id": hit["chunk_id"],
                "score": hit["score"],
                "filename": chunk["filename"],
                "page": chunk["page"],
                "text": chunk["text"],
            }
        )
    return results


def _print_results(query: str) -> None:
    results = retrieve(query)
    print(f"query: {query!r}\n")
    for r in results:
        preview = r["text"].replace("\n", " ")[:150]
        print(f"score={r['score']:.3f}  {r['filename']}, page {r['page']}")
        print(f"  {preview!r}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: uv run python -m rag.retrieve <question>")
        raise SystemExit(1)
    _print_results(" ".join(sys.argv[1:]))
