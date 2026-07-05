#!/usr/bin/env python3
"""Evaluate retrieval quality per chunking strategy.

For every question in evaluation/questions.csv and every strategy, records:
top-1 document, top-1 similarity, hit@k (expected doc appears in top-k),
grounding verdict, and certification flag. Writes evaluation/results.csv.

Retrieval-only by default. Pass --generate to also call the LLM (requires a
running Ollama with the model pulled).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.chunking import CHUNKERS  # noqa: E402
from rag.indexing import load_index  # noqa: E402
from rag.retrieval import retrieve  # noqa: E402
from rag.safety import assess  # noqa: E402

QUESTIONS_CSV = PROJECT_ROOT / "evaluation" / "questions.csv"
RESULTS_CSV = PROJECT_ROOT / "evaluation" / "results.csv"

FIELDNAMES = [
    "question_id", "strategy", "question_type", "expected_doc",
    "top1_doc", "top1_score", "hit_at_k", "grounding",
    "certification_flag", "answer",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--generate", action="store_true",
                        help="Also generate answers with the local Ollama model")
    args = parser.parse_args()

    with open(QUESTIONS_CSV, encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    indexes = {s: load_index(s) for s in sorted(CHUNKERS)}

    rows = []
    for strategy in sorted(CHUNKERS):
        for q in questions:
            retrieved = retrieve(q["question"], strategy, args.top_k,
                                 index_and_chunks=indexes[strategy])
            verdict = assess(q["question"], retrieved)

            expected = q["expected_doc"]
            retrieved_docs = [r["doc_name"] for r in retrieved]
            hit = int(bool(expected) and expected in retrieved_docs)

            answer = ""
            if args.generate and verdict.should_answer:
                from rag.generation import build_prompt, generate_ollama, GenerationError
                try:
                    answer = generate_ollama(build_prompt(q["question"], retrieved))
                except GenerationError as exc:
                    answer = f"[generation failed: {exc}]"

            rows.append({
                "question_id": q["question_id"],
                "strategy": strategy,
                "question_type": q["question_type"],
                "expected_doc": expected,
                "top1_doc": retrieved_docs[0] if retrieved_docs else "",
                "top1_score": f"{retrieved[0]['score']:.4f}" if retrieved else "",
                "hit_at_k": hit,
                "grounding": verdict.grounding,
                "certification_flag": int(verdict.certification_flag),
                "answer": answer,
            })
            print(f"{strategy:<10} {q['question_id']}  top1={rows[-1]['top1_doc']:<28} "
                  f"score={rows[-1]['top1_score']:<7} hit@{args.top_k}={hit} "
                  f"grounding={verdict.grounding}")

    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    # summary: hit@k per strategy over in-scope questions
    print("\nhit@k on in-scope questions:")
    for strategy in sorted(CHUNKERS):
        scoped = [r for r in rows
                  if r["strategy"] == strategy and r["question_type"] == "in_scope"]
        hits = sum(r["hit_at_k"] for r in scoped)
        print(f"  {strategy:<10} {hits}/{len(scoped)}")
    print(f"\nResults written to {RESULTS_CSV}")


if __name__ == "__main__":
    main()
    # On macOS the faiss/torch OpenMP runtimes can segfault during normal
    # interpreter teardown after all work is done. Flush and exit hard so the
    # script reliably reports success.
    sys.stdout.flush()
    os._exit(0)
