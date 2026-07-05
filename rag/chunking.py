"""Chunking strategies for RAG over Markdown documents.

Each chunker is a pure function that takes the document text and metadata and
returns a list of chunk dicts with the schema:

    {
        "chunk_id": str,   # deterministic: "<doc_id>::<strategy>::<i:04d>"
        "doc_id": str,
        "doc_name": str,   # source filename
        "strategy": str,
        "text": str,
        "section": str | None,  # nearest Markdown heading, if known
        "start_char": int,
    }
"""

from __future__ import annotations

import re

DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 50
DEFAULT_SECTION_MAX_CHARS = 1200

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


def _make_chunk(doc_id: str, doc_name: str, strategy: str, index: int,
                text: str, section: str | None, start_char: int) -> dict:
    return {
        "chunk_id": f"{doc_id}::{strategy}::{index:04d}",
        "doc_id": doc_id,
        "doc_name": doc_name,
        "strategy": strategy,
        "text": text.strip(),
        "section": section,
        "start_char": start_char,
    }


def fixed_size_chunks(text: str, doc_id: str, doc_name: str,
                      chunk_size: int = DEFAULT_CHUNK_SIZE,
                      overlap: int = DEFAULT_OVERLAP) -> list[dict]:
    """Character windows of ~chunk_size with overlap, broken at whitespace."""
    chunks = []
    pos = 0
    index = 0
    n = len(text)
    while pos < n:
        end = min(pos + chunk_size, n)
        if end < n:
            # back up to nearest whitespace so words are not split
            space = text.rfind(" ", pos, end)
            newline = text.rfind("\n", pos, end)
            cut = max(space, newline)
            if cut > pos:
                end = cut
        piece = text[pos:end]
        if piece.strip():
            chunks.append(_make_chunk(doc_id, doc_name, "fixed", index,
                                      piece, None, pos))
            index += 1
        if end >= n:
            break
        pos = max(end - overlap, pos + 1)
    return chunks


def _split_recursive(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    """Split text so each piece is <= chunk_size, preferring larger separators."""
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        # no separator left: hard split
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    sep, rest = separators[0], separators[1:]
    parts = text.split(sep)

    pieces: list[str] = []
    current = ""
    for part in parts:
        candidate = current + sep + part if current else part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                pieces.append(current)
            if len(part) > chunk_size:
                pieces.extend(_split_recursive(part, chunk_size, rest))
                current = ""
            else:
                current = part
    if current:
        pieces.append(current)
    return pieces


def recursive_chunks(text: str, doc_id: str, doc_name: str,
                     chunk_size: int = DEFAULT_CHUNK_SIZE,
                     overlap: int = DEFAULT_OVERLAP,
                     separators: list[str] | None = None) -> list[dict]:
    """Recursive character splitting on paragraph, line, sentence, word."""
    if separators is None:
        separators = ["\n\n", "\n", ". ", " "]
    pieces = [p for p in _split_recursive(text, chunk_size, separators) if p.strip()]

    chunks = []
    search_from = 0
    for index, piece in enumerate(pieces):
        start = text.find(piece[:60], search_from)
        if start == -1:
            start = search_from
        search_from = start + len(piece)
        if overlap and index > 0:
            tail = pieces[index - 1][-overlap:]
            piece = tail + " " + piece
        chunks.append(_make_chunk(doc_id, doc_name, "recursive", index,
                                  piece, None, start))
    return chunks


def section_aware_chunks(text: str, doc_id: str, doc_name: str,
                         max_chars: int = DEFAULT_SECTION_MAX_CHARS) -> list[dict]:
    """Split on Markdown headings (H1-H3), keeping heading as section metadata.

    Oversized sections are sub-split with the recursive splitter, each part
    retaining the section heading (prepended so the embedding sees it).
    """
    matches = list(_HEADING_RE.finditer(text))
    sections: list[tuple[str | None, int, str]] = []  # (heading, start, body)

    if not matches:
        sections.append((None, 0, text))
    else:
        if matches[0].start() > 0:
            sections.append((None, 0, text[:matches[0].start()]))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            heading = m.group(2).strip()
            body = text[m.end():end]
            sections.append((heading, m.start(), body))

    chunks = []
    index = 0
    for heading, start, body in sections:
        if not body.strip():
            continue
        prefix = f"{heading}\n\n" if heading else ""
        full = prefix + body.strip()
        if len(full) <= max_chars:
            parts = [full]
        else:
            parts = [prefix + p.strip() for p in
                     _split_recursive(body.strip(), max_chars - len(prefix),
                                      ["\n\n", "\n", ". ", " "])
                     if p.strip()]
        for part in parts:
            chunks.append(_make_chunk(doc_id, doc_name, "section", index,
                                      part, heading, start))
            index += 1
    return chunks


CHUNKERS = {
    "fixed": fixed_size_chunks,
    "recursive": recursive_chunks,
    "section": section_aware_chunks,
}

STRATEGY_LABELS = {
    "fixed": "Fixed-size",
    "recursive": "Recursive",
    "section": "Section-aware",
}
