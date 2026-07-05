#!/usr/bin/env python3
"""Build FAISS indexes over the combined corpus: synthetic sample docs + the
real-world HSE source pages fetched by scripts/fetch_hse_sources.py.

This is a separate, opt-in operation. scripts/build_indexes.py is left
untouched and keeps its default behaviour (sample_documents only). Run this
script instead when you want the stronger, real-world-sourced corpus:

    python scripts/seed_hse_corpus.py

It overwrites the same data/processed/chunks_<strategy>.jsonl and
data/indexes/<strategy>/ outputs that build_indexes.py writes, since the app
and evaluate.py always read from those fixed paths.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.chunking import CHUNKERS  # noqa: E402
from rag.indexing import build_index  # noqa: E402

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_documents"
HSE_DIR = PROJECT_ROOT / "data" / "raw_sources" / "hse"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n\n?", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def load_documents() -> list[tuple[str, str, str]]:
    """Return sorted list of (doc_id, doc_name, text) from both doc directories."""
    docs = []
    for docs_dir in (SAMPLE_DIR, HSE_DIR):
        for path in sorted(docs_dir.glob("*.md")):
            text = _strip_frontmatter(path.read_text(encoding="utf-8"))
            docs.append((path.stem, path.name, text))
    if not docs:
        raise SystemExit(f"No Markdown documents found in {SAMPLE_DIR} or {HSE_DIR}")
    return docs


def main() -> None:
    docs = load_documents()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(docs)} documents ({SAMPLE_DIR.name} + {HSE_DIR.relative_to(PROJECT_ROOT)})")
    for strategy in sorted(CHUNKERS):
        chunker = CHUNKERS[strategy]
        chunks = []
        for doc_id, doc_name, text in docs:
            chunks.extend(chunker(text, doc_id=doc_id, doc_name=doc_name))

        processed_path = PROCESSED_DIR / f"chunks_{strategy}.jsonl"
        with open(processed_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        out_dir = build_index(chunks, strategy)
        print(f"  {strategy:<10} {len(chunks):>4} chunks -> {out_dir}")

    print("Done.")


if __name__ == "__main__":
    main()
    # On macOS the faiss/torch OpenMP runtimes can segfault during normal
    # interpreter teardown after all work is done. Flush and exit hard so the
    # script reliably reports success.
    sys.stdout.flush()
    os._exit(0)
