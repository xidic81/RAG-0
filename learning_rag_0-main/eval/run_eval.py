"""Evaluation harness. specs.md §8.

Two things: recall@k (retrieval only, no LLM, runs in seconds -- the
metric you'll use for almost every experiment in specs.md §9) and answer
accuracy (needs the LLM, graded by hand). Run recall first. If it's low,
nothing downstream can save you, so there's no point running answers yet.

Usage:
    uv run python -m eval.run_eval recall
    uv run python -m eval.run_eval answers
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from rag.retrieve import retrieve

TESTSET_PATH = Path(__file__).parent / "testset.csv"


def load_testset() -> list[dict]:
    with open(TESTSET_PATH) as f:
        return list(csv.DictReader(f))


def _expected_pairs(row: dict) -> list[tuple[str, int]]:
    filenames = [f.strip() for f in row["filename"].split(";")]
    pages = [int(p.strip()) for p in row["page"].split(";")]
    return list(zip(filenames, pages))


def run_recall(top_k: int = 5) -> None:
    rows = load_testset()
    hits_by_category: dict[str, list[bool]] = defaultdict(list)
    unanswerable_scores = []

    for row in rows:
        results = retrieve(row["question"], top_k=top_k)
        retrieved_pairs = {(r["filename"], r["page"]) for r in results}

        if row["category"] == "unanswerable":
            top_score = results[0]["score"] if results else 0.0
            unanswerable_scores.append(top_score)
            print(f"[unanswerable] top score={top_score:.3f}  {row['question']}")
            continue

        expected = _expected_pairs(row)
        hit = all(pair in retrieved_pairs for pair in expected)
        hits_by_category[row["category"]].append(hit)
        print(f"[{'HIT ' if hit else 'MISS'}] #{row['id']} ({row['category']}) {row['question']}")

    print(f"\n--- recall@{top_k} ---")
    all_hits: list[bool] = []
    for category, hits in hits_by_category.items():
        all_hits += hits
        print(f"{category:12s} {sum(hits)}/{len(hits)}  ({sum(hits) / len(hits):.0%})")
    print(f"{'overall':12s} {sum(all_hits)}/{len(all_hits)}  ({sum(all_hits) / len(all_hits):.0%})")

    if unanswerable_scores:
        print(f"\nunanswerable top scores: {[f'{s:.3f}' for s in unanswerable_scores]}")
        print("specs.md §6.2: set SCORE_THRESHOLD in rag/chat.py just below this band.")


def run_answers() -> None:
    from rag.chat import ask

    rows = [r for r in load_testset() if r["category"] != "unanswerable"]
    out_path = Path(__file__).parent / "results.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "question", "expected_answer", "actual_answer", "correct(y/n)"])
        for row in rows:
            result = ask(row["question"])
            print(f"#{row['id']}: {row['question']}")
            print(f"  expected: {row['expected_answer']}")
            print(f"  actual:   {result['answer']}\n")
            writer.writerow([row["id"], row["question"], row["expected_answer"], result["answer"], ""])
    print(f"wrote {out_path} -- grade the 'correct(y/n)' column by hand.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "recall"
    if mode == "recall":
        run_recall()
    elif mode == "answers":
        run_answers()
    else:
        print("usage: uv run python -m eval.run_eval [recall|answers]")
        raise SystemExit(1)
