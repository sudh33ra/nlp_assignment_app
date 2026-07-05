"""Query-time retrieval against a per-strategy FAISS index."""

from __future__ import annotations

from rag.embeddings import embed_texts
from rag.indexing import load_index


def retrieve(query: str, strategy: str, top_k: int = 4,
             index_and_chunks=None) -> list[dict]:
    """Return top_k chunks for the query, sorted by cosine similarity.

    index_and_chunks lets callers (e.g. Streamlit with cache_resource)
    pass a preloaded (index, chunks) tuple to avoid re-reading from disk.
    """
    if index_and_chunks is None:
        index_and_chunks = load_index(strategy)
    index, chunks = index_and_chunks

    query_vec = embed_texts([query])
    top_k = min(top_k, index.ntotal)
    scores, ids = index.search(query_vec, top_k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        chunk = chunks[idx]
        results.append({
            "doc_name": chunk["doc_name"],
            "doc_id": chunk["doc_id"],
            "chunk_id": chunk["chunk_id"],
            "section": chunk.get("section"),
            "score": float(score),
            "text": chunk["text"],
        })
    return results
