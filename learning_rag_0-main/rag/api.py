"""FastAPI wrapper around the RAG pipeline. specs.md §7.

Every endpoint here is a thin layer over functions the earlier steps
already built and tested from the command line -- rag.chat.ask() is the
whole /chat handler, rag.ingest.ingest_document() is the whole /documents
upload handler. The API's only new job is HTTP plumbing and persisting
conversation history.

Run: uv run uvicorn rag.api:app --reload
"""

from __future__ import annotations

import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel

from rag import db, pinecone_store
from rag.chat import ask
from rag.config import settings
from rag.ingest import ingest_document


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create any missing tables before serving, so a fresh database works
    # without a manual psql step. A failure here is logged, not fatal: the
    # API still starts and GET /health reports what's wrong.
    try:
        with db.connect() as conn:
            db.init_schema(conn)
    except Exception as exc:
        print(f"schema init failed: {exc}")
    yield


app = FastAPI(title="RAG Chatbot", lifespan=lifespan)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    citations: list[dict]


@app.post("/documents")
async def upload_document(file: UploadFile, background_tasks: BackgroundTasks) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF files are supported")

    # The filename comes straight from the client -- keep only its last
    # path component so "../../x.pdf" can't write outside UPLOAD_DIR.
    filename = Path(file.filename).name

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Ingestion is I/O and embedding-bound, easily tens of seconds for a
    # real document -- run it after the response, not before it. Poll
    # GET /documents to see status move pending -> processing -> ready.
    background_tasks.add_task(ingest_document, dest)
    return {"filename": filename, "status": "queued"}


@app.get("/documents")
def list_documents() -> list[dict]:
    with db.connect() as conn:
        return db.list_documents(conn)


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str) -> dict:
    with db.connect() as conn:
        existing = conn.execute("SELECT id FROM documents WHERE id = %s::uuid", (doc_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "document not found")
        db.delete_document(conn, doc_id)  # cascades to chunks in Postgres
    pinecone_store.delete_by_doc(doc_id)  # vectors live in a separate store, deleted separately
    return {"deleted": doc_id}


@app.post("/conversations")
def create_conversation() -> dict:
    conversation_id = str(uuid.uuid4())
    with db.connect() as conn:
        db.create_conversation(conn, conversation_id)
    return {"conversation_id": conversation_id}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    with db.connect() as conn:
        conversation_id = req.conversation_id
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
            db.create_conversation(conn, conversation_id)
        elif db.find_conversation(conn, conversation_id) is None:
            raise HTTPException(404, "conversation not found")

        result = ask(req.message)

        db.insert_message(conn, str(uuid.uuid4()), conversation_id, "user", req.message)
        assistant_msg_id = str(uuid.uuid4())
        db.insert_message(
            conn,
            assistant_msg_id,
            conversation_id,
            "assistant",
            result["answer"],
            citations=result["citations"],
            retrieval_debug=result["retrieval_debug"],
        )

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=assistant_msg_id,
        answer=result["answer"],
        citations=result["citations"],
    )


@app.get("/health")
def health() -> dict:
    status = {}

    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
        status["postgres"] = "ok"
    except Exception as exc:
        status["postgres"] = f"error: {exc}"

    try:
        pinecone_store._client().list_indexes()
        status["pinecone"] = "ok"
    except Exception as exc:
        status["pinecone"] = f"error: {exc}"

    status["llm_provider"] = "ollama" if settings.use_ollama else "groq"
    try:
        import requests

        if settings.use_ollama:
            requests.get(f"{settings.ollama_host}/api/version", timeout=3).raise_for_status()
        else:
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is not configured")
            requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                timeout=5,
            ).raise_for_status()
        status["llm"] = "ok"
    except Exception as exc:
        status["llm"] = f"error: {exc}"

    return status
