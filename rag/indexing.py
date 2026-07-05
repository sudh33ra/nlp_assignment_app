"""FAISS index build/load, one index directory per chunking strategy."""

from __future__ import annotations

import json
from pathlib import Path

import faiss

from rag.embeddings import embed_texts

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_ROOT = PROJECT_ROOT / "data" / "indexes"


def index_dir(strategy: str) -> Path:
    return INDEX_ROOT / strategy


def build_index(chunks: list[dict], strategy: str) -> Path:
    """Embed chunks and write index.faiss + chunks.jsonl for the strategy."""
    if not chunks:
        raise ValueError(f"No chunks provided for strategy '{strategy}'")

    out_dir = index_dir(strategy)
    out_dir.mkdir(parents=True, exist_ok=True)

    vectors = embed_texts([c["text"] for c in chunks])
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    faiss.write_index(index, str(out_dir / "index.faiss"))
    with open(out_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return out_dir


def load_index(strategy: str):
    """Load (faiss_index, chunks) for a strategy, with a helpful error."""
    out_dir = index_dir(strategy)
    index_path = out_dir / "index.faiss"
    chunks_path = out_dir / "chunks.jsonl"
    if not index_path.exists() or not chunks_path.exists():
        raise FileNotFoundError(
            f"No index found for strategy '{strategy}' in {out_dir}. "
            "Build it first with: python scripts/build_indexes.py"
        )
    index = faiss.read_index(str(index_path))
    with open(chunks_path, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    if index.ntotal != len(chunks):
        raise RuntimeError(
            f"Index/metadata mismatch for '{strategy}': {index.ntotal} vectors "
            f"vs {len(chunks)} chunks. Rebuild with scripts/build_indexes.py"
        )
    return index, chunks
