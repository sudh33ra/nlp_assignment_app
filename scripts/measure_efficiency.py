#!/usr/bin/env python3
"""Timing wrapper around the existing chunking/embedding/retrieval code paths.

Measures, per chunking strategy, over the currently-committed corpus
(sample_documents + data/raw_sources/hse, same set scripts/seed_hse_corpus.py
indexes):

  - number of generated chunks
  - index build time (embedding + FAISS IndexFlatIP construction, in memory --
    this does NOT write to data/indexes/ or data/processed/, so it never
    touches the committed index artifacts)
  - retrieval time per evaluation question, against the already-committed
    on-disk index (data/indexes/<strategy>/), using the same top_k=4 default
    as scripts/evaluate.py

Writes:
    evaluation/efficiency_metrics.csv
    evaluation/efficiency_metrics.md
    evaluation/efficiency_chart_data.csv

Usage:
    python scripts/measure_efficiency.py
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import rag  # noqa: F401, E402  (imports torch before faiss -- see rag/__init__.py)
import faiss  # noqa: E402

from rag.chunking import CHUNKERS  # noqa: E402
from rag.embeddings import embed_texts  # noqa: E402
from rag.indexing import load_index  # noqa: E402
from rag.retrieval import retrieve  # noqa: E402
from seed_hse_corpus import load_documents  # noqa: E402

QUESTIONS_CSV = PROJECT_ROOT / "evaluation" / "questions.csv"
OUT_CSV = PROJECT_ROOT / "evaluation" / "efficiency_metrics.csv"
OUT_MD = PROJECT_ROOT / "evaluation" / "efficiency_metrics.md"
OUT_CHART_CSV = PROJECT_ROOT / "evaluation" / "efficiency_chart_data.csv"

TOP_K = 4

# Known from the earlier assignment evaluation run (scripts/evaluate.py
# --generate on 2026-07-06); not re-measured here since this script only
# times chunking/indexing/retrieval, not generation.
KNOWN_GENERATION_RUN = {
    "total_wall_time_seconds": 645,  # 10m 45s
    "total_rows": 120,
    "generated_answers": 108,
    "pre_generation_refusals": 12,
}


def main() -> None:
    with open(QUESTIONS_CSV, encoding="utf-8") as f:
        questions = [row["question"] for row in csv.DictReader(f)]
    n_questions = len(questions)

    docs = load_documents()
    print(f"Loaded {len(docs)} documents for chunking/index-build timing")

    # Warm up the embedding model once so its one-time load cost doesn't leak
    # into the first strategy's measurements.
    embed_texts(["warm-up"])

    rows = []
    for strategy in sorted(CHUNKERS):
        chunker = CHUNKERS[strategy]

        chunks = []
        for doc_id, doc_name, text in docs:
            chunks.extend(chunker(text, doc_id=doc_id, doc_name=doc_name))
        num_chunks = len(chunks)

        # Index build time: embedding all chunks + building the FAISS index,
        # in memory only (mirrors rag/indexing.py:build_index without the
        # disk writes, so it never touches the committed data/indexes/ files).
        build_start = time.perf_counter()
        vectors = embed_texts([c["text"] for c in chunks])
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        index_build_time = time.perf_counter() - build_start

        # Retrieval timing against the already-committed on-disk index.
        index_and_chunks = load_index(strategy)
        retrieve(questions[0], strategy, TOP_K, index_and_chunks=index_and_chunks)  # warm-up call

        latencies_ms = []
        for q in questions:
            t0 = time.perf_counter()
            retrieve(q, strategy, TOP_K, index_and_chunks=index_and_chunks)
            latencies_ms.append((time.perf_counter() - t0) * 1000)

        row = {
            "strategy": strategy,
            "num_chunks": num_chunks,
            "index_build_time_seconds": round(index_build_time, 4),
            "avg_retrieval_ms": round(statistics.mean(latencies_ms), 3),
            "median_retrieval_ms": round(statistics.median(latencies_ms), 3),
            "min_retrieval_ms": round(min(latencies_ms), 3),
            "max_retrieval_ms": round(max(latencies_ms), 3),
            "num_questions": n_questions,
        }
        rows.append(row)
        print(f"{strategy:<10} chunks={num_chunks:>4}  build={index_build_time:.3f}s  "
              f"avg_retrieval={row['avg_retrieval_ms']:.2f}ms  "
              f"median={row['median_retrieval_ms']:.2f}ms  "
              f"min={row['min_retrieval_ms']:.2f}ms  max={row['max_retrieval_ms']:.2f}ms")

    fieldnames = ["strategy", "num_chunks", "index_build_time_seconds",
                  "avg_retrieval_ms", "median_retrieval_ms",
                  "min_retrieval_ms", "max_retrieval_ms", "num_questions"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with open(OUT_CHART_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["strategy", "metric", "value"])
        for row in rows:
            writer.writerow([row["strategy"], "num_chunks", row["num_chunks"]])
            writer.writerow([row["strategy"], "index_build_time_seconds", row["index_build_time_seconds"]])
            writer.writerow([row["strategy"], "avg_retrieval_ms", row["avg_retrieval_ms"]])
            writer.writerow([row["strategy"], "median_retrieval_ms", row["median_retrieval_ms"]])

    md_lines = [
        "# Efficiency Metrics by Chunking Strategy",
        "",
        f"Measured on {n_questions} evaluation questions "
        f"(`evaluation/questions.csv`), top_k={TOP_K}, against the "
        "currently-committed combined corpus (sample_documents + "
        "data/raw_sources/hse, 46 documents). Index build time is measured "
        "in memory (embedding + FAISS `IndexFlatIP.add`), matching "
        "`rag/indexing.py:build_index` minus the disk write; retrieval "
        "timing uses the already-committed on-disk index "
        "(`data/indexes/<strategy>/`), matching the code path used by "
        "`scripts/evaluate.py` and the Streamlit app.",
        "",
        "| Strategy | Chunks | Index build time (s) | Avg retrieval (ms) | "
        "Median retrieval (ms) | Min retrieval (ms) | Max retrieval (ms) | "
        "Questions |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        md_lines.append(
            f"| {row['strategy']} | {row['num_chunks']} | "
            f"{row['index_build_time_seconds']:.3f} | {row['avg_retrieval_ms']:.2f} | "
            f"{row['median_retrieval_ms']:.2f} | {row['min_retrieval_ms']:.2f} | "
            f"{row['max_retrieval_ms']:.2f} | {row['num_questions']} |"
        )

    g = KNOWN_GENERATION_RUN
    md_lines += [
        "",
        "## Full generation run (known, not re-measured by this script)",
        "",
        "This script times chunking/indexing/retrieval only, not LLM "
        "generation. The generation-inclusive run below is the figure from "
        "the earlier assignment evaluation run "
        "(`python scripts/evaluate.py --generate`, local Ollama "
        "`qwen2.5:0.5b`, 2026-07-06), reported here for completeness, not "
        "re-measured by this script:",
        "",
        f"- Total wall time: {g['total_wall_time_seconds']}s "
        f"(10m 45s) for {g['total_rows']} result rows "
        f"(40 questions x 3 strategies)",
        f"- Generated answers: {g['generated_answers']}",
        f"- Pre-generation weak-evidence refusals (no LLM call made): "
        f"{g['pre_generation_refusals']}",
        f"- Rough average per call (includes retrieval): "
        f"~{g['total_wall_time_seconds'] / g['generated_answers']:.2f}s "
        "-- informal, not logged by the evaluation code itself",
    ]
    OUT_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"\nWrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_CHART_CSV}")


if __name__ == "__main__":
    main()
    # See scripts/build_indexes.py for why this hard-exit exists on macOS.
    sys.stdout.flush()
    import os
    os._exit(0)
