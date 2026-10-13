"""The full RAG loop: retrieve, maybe refuse, generate. specs.md §5-6.

This is the one function specs.md §7.1's /chat endpoint will eventually
just wrap.
"""

from __future__ import annotations

import sys

from rag import generate as gen
from rag.retrieve import retrieve

REFUSAL_MESSAGE = "I couldn't find this in the documents."

# specs.md §6.2: measured, not guessed, against eval/testset.csv on the
# sample corpus (`uv run python -m eval.run_eval recall`). The 5
# unanswerable questions topped out at 0.342; the 20 answerable ones never
# dropped below 0.388. 0.36 sits in that gap. Cosine scores aren't
# calibrated probabilities, so re-measure this if you change the corpus.
SCORE_THRESHOLD = 0.36


def ask(question: str) -> dict:
    """Returns {"answer", "citations", "retrieval_debug"}."""
    chunks = retrieve(question)
    retrieval_debug = [{"chunk_id": c["chunk_id"], "score": c["score"]} for c in chunks]

    if not chunks or chunks[0]["score"] < SCORE_THRESHOLD:
        return {"answer": REFUSAL_MESSAGE, "citations": [], "retrieval_debug": retrieval_debug}

    answer_text = gen.answer(question, chunks)
    citations = [{"filename": c["filename"], "page": c["page"]} for c in chunks]
    return {"answer": answer_text, "citations": citations, "retrieval_debug": retrieval_debug}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: uv run python -m rag.chat <question>")
        raise SystemExit(1)
    result = ask(" ".join(sys.argv[1:]))
    print(result["answer"])
    print()
    print("citations:", result["citations"])
