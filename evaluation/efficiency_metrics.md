# Efficiency Metrics by Chunking Strategy

Measured on 40 evaluation questions (`evaluation/questions.csv`), top_k=4, against the currently-committed combined corpus (sample_documents + data/raw_sources/hse, 46 documents). Index build time is measured in memory (embedding + FAISS `IndexFlatIP.add`), matching `rag/indexing.py:build_index` minus the disk write; retrieval timing uses the already-committed on-disk index (`data/indexes/<strategy>/`), matching the code path used by `scripts/evaluate.py` and the Streamlit app.

| Strategy | Chunks | Index build time (s) | Avg retrieval (ms) | Median retrieval (ms) | Min retrieval (ms) | Max retrieval (ms) | Questions |
|---|---|---|---|---|---|---|---|
| fixed | 497 | 12.291 | 14.65 | 14.50 | 11.51 | 21.64 | 40 |
| recursive | 601 | 12.509 | 14.57 | 14.06 | 11.79 | 21.30 | 40 |
| section | 334 | 12.237 | 13.72 | 13.38 | 11.58 | 16.64 | 40 |

## Full generation run (known, not re-measured by this script)

This script times chunking/indexing/retrieval only, not LLM generation. The generation-inclusive run below is the figure from the earlier assignment evaluation run (`python scripts/evaluate.py --generate`, local Ollama `qwen2.5:0.5b`, 2026-07-06), reported here for completeness, not re-measured by this script:

- Total wall time: 645s (10m 45s) for 120 result rows (40 questions x 3 strategies)
- Generated answers: 108
- Pre-generation weak-evidence refusals (no LLM call made): 12
- Rough average per call (includes retrieval): ~5.97s -- informal, not logged by the evaluation code itself
