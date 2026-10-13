"""Every setting the rest of this project reads, all in one place."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    postgres_dsn: str
    pinecone_api_key: str
    pinecone_index: str
    use_ollama: bool
    ollama_host: str
    ollama_model: str
    groq_api_key: str
    groq_model: str


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    return Settings(
        postgres_dsn=env.get("POSTGRES_DSN", "postgresql://rag:rag@localhost:5432/rag"),
        pinecone_api_key=env.get("PINECONE_API_KEY", ""),
        pinecone_index=env.get("PINECONE_INDEX", "rag-chatbot"),
        use_ollama=env.get("USE_OLLAMA", "false").strip().lower() == "true",
        ollama_host=env.get("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=env.get("OLLAMA_MODEL", "hadad/LFM2.5-1.2B:Q4_K_M"),
        groq_api_key=env.get("GROQ_API_KEY", ""),
        groq_model=env.get("GROQ_MODEL", "openai/gpt-oss-120b"),
    )


settings = load_settings()
