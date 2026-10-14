"""LLM generation. specs.md §6.

Kept behind one function, generate(messages) -> str, so swapping Ollama
for a hosted model later is a config change, not a refactor.
"""

from __future__ import annotations

from pathlib import Path

import requests

from rag.config import settings

_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "system_prompt.txt").read_text()


def generate(messages: list[dict]) -> str:
    """messages: [{"role": "user"|"assistant"|"system", "content": ...}]"""
    if settings.use_ollama:
        resp = requests.post(
            f"{settings.ollama_host}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 8192},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        json={
            "model": settings.groq_model,
            "messages": messages,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def format_context(chunks: list[dict]) -> str:
    """chunks: [{"filename": ..., "page": ..., "text": ...}, ...]"""
    parts = [f"[{c['filename']}, page {c['page']}]\n{c['text']}" for c in chunks]
    return "\n\n".join(parts)


def answer(question: str, chunks: list[dict]) -> str:
    prompt = _PROMPT_TEMPLATE.format(context=format_context(chunks), question=question)
    return generate([{"role": "user", "content": prompt}])
