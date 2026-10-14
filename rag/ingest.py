"""Ingestion: load -> split -> store -> embed. specs.md §4."""

from __future__ import annotations

import hashlib
import pickle
import sys
import uuid
from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag import db, pinecone_store

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "extract_cache"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_pages(path: Path, file_hash: str) -> list[Document]:
    """specs.md §4.1: cache the loader's output keyed by file_hash. You'll
    re-run chunking many times while tuning chunk_size (Exercise 1), and
    re-parsing every page of a 200-PDF corpus on each attempt makes that
    loop unbearable.
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"{file_hash}.pkl"
    if cache_path.exists():
        return pickle.loads(cache_path.read_bytes())
    pages = PyMuPDFLoader(str(path)).load()
    cache_path.write_bytes(pickle.dumps(pages))
    return pages


def load_and_split(path: str | Path, file_hash: str | None = None) -> list[Document]:
    """Load a PDF (one Document per page) and split it into chunks.

    Each chunk inherits metadata["source"] and metadata["page"] from the
    page it was cut from -- that inheritance is the entire citation layer,
    no manual page tracking needed.
    """
    path = Path(path)
    pages = _load_pages(path, file_hash or file_sha256(path))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    return splitter.split_documents(pages)


def ingest_document(path: str | Path) -> str:
    """Ingest one PDF: Postgres gets the text, Pinecone gets the vectors,
    both keyed by the same chunk id. specs.md §4.2 idempotency: an
    unchanged file (same sha256) is a no-op; re-ingesting a changed or
    previously-failed one deletes its old rows/vectors first.
    """
    path = Path(path)
    file_hash = file_sha256(path)

    with db.connect() as conn:
        existing = db.find_document_by_hash(conn, file_hash)
        if existing and existing["status"] == "ready":
            print(f"skip {path.name}: already ingested (doc {existing['id']})")
            return str(existing["id"])
        if existing:
            db.delete_document(conn, str(existing["id"]))
            pinecone_store.delete_by_doc(str(existing["id"]))

        doc_id = str(uuid.uuid4())
        db.insert_document(conn, doc_id, path.name, file_hash, status="pending")

        chunks = load_and_split(path, file_hash=file_hash)
        page_count = chunks[-1].metadata["page"] + 1 if chunks else 0
        db.mark_processing(conn, doc_id, page_count)

        # PyMuPDFLoader's page metadata is 0-indexed; +1 so citations match
        # the page number a human sees when they open the PDF.
        chunk_rows = [
            (str(uuid.uuid4()), doc_id, chunk.metadata["page"] + 1, chunk.page_content) for chunk in chunks
        ]
        db.insert_chunks(conn, chunk_rows)

        try:
            pinecone_store.ensure_index()
            records = [
                {"_id": chunk_id, "text": text, "doc_id": doc_id, "page": page}
                for chunk_id, _doc_id, page, text in chunk_rows
            ]
            pinecone_store.upsert_chunks(records)
        except Exception as exc:
            db.update_document_status(conn, doc_id, "failed", str(exc))
            raise
        else:
            db.update_document_status(conn, doc_id, "ready")

    print(f"ingested {path.name}: {len(chunk_rows)} chunks (doc {doc_id})")
    return doc_id


def _inspect(path: str) -> None:
    chunks = load_and_split(path)
    print(f"{path}: {len(chunks)} chunks from {chunks[-1].metadata['page'] + 1} pages\n")
    for i, chunk in enumerate(chunks[:5]):
        preview = chunk.page_content.replace("\n", " ")[:150]
        print(f"[{i}] page={chunk.metadata['page']}  chars={len(chunk.page_content)}")
        print(f"    {preview!r}\n")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("inspect", "run"):
        print("usage: uv run python -m rag.ingest inspect|run <path-to-pdf>")
        raise SystemExit(1)
    command, pdf_path = sys.argv[1], sys.argv[2]
    if command == "inspect":
        _inspect(pdf_path)
    else:
        ingest_document(pdf_path)
