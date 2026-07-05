"""Embedding model wrapper (sentence-transformers/all-MiniLM-L6-v2)."""

from __future__ import annotations

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_embedder = None


def get_embedder():
    """Lazily load and cache the sentence-transformers model."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(MODEL_NAME)
    return _embedder


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return L2-normalised float32 embeddings (so inner product = cosine)."""
    model = get_embedder()
    vectors = model.encode(texts, normalize_embeddings=True,
                           show_progress_bar=False)
    return np.asarray(vectors, dtype="float32")
