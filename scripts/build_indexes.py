#!/usr/bin/env python3
"""Build FAISS indexes for each chunking strategy.

Reads data/sample_documents/*.md, chunks each document with every strategy
(or one chosen via --strategy), writes:

    data/processed/chunks_<strategy>.jsonl
    data/indexes/<strategy>/index.faiss
    data/indexes/<strategy>/chunks.jsonl

Deterministic: files are processed in sorted order with fixed parameters.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rag.chunking import CHUNKERS  # noqa: E402
from rag.indexing import build_index  # noqa: E402

DOCS_DIR = PROJECT_ROOT / "data" / "sample_documents"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def load_documents() -> list[tuple[str, str, str]]:
    """Return sorted list of (doc_id, doc_name, text)."""
    docs = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        docs.append((path.stem, path.name, path.read_text(encoding="utf-8")))
    if not docs:
        raise SystemExit(f"No Markdown documents found in {DOCS_DIR}")
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=sorted(CHUNKERS),
                        help="Rebuild only this strategy (default: all)")
    args = parser.parse_args()

    strategies = [args.strategy] if args.strategy else sorted(CHUNKERS)
    docs = load_documents()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(docs)} documents from {DOCS_DIR}")
    for strategy in strategies:
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
