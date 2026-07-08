"""Recursive character-based chunker tuned for biomedical text."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "]


@dataclass
class Chunk:
    text: str
    index: int


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[Chunk]:
    """Split text into overlapping chunks of ~chunk_size characters."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [Chunk(text=text, index=0)]

    # First, split on paragraph boundaries; then greedily pack.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for p in paragraphs:
        if len(p) > chunk_size:
            # Recursively split large paragraphs by sentences
            for piece in _split_hard(p, chunk_size):
                buf = _accumulate(buf, piece, chunk_size, chunks)
        else:
            buf = _accumulate(buf, p, chunk_size, chunks)
    if buf:
        chunks.append(buf)

    # Add overlap
    if overlap > 0 and len(chunks) > 1:
        with_overlap: List[str] = []
        for i, c in enumerate(chunks):
            if i == 0:
                with_overlap.append(c)
            else:
                tail = chunks[i - 1][-overlap:]
                with_overlap.append(tail + "\n" + c)
        chunks = with_overlap

    return [Chunk(text=c, index=i) for i, c in enumerate(chunks)]


def _accumulate(buf: str, piece: str, chunk_size: int, out: List[str]) -> str:
    if not buf:
        return piece
    if len(buf) + len(piece) + 1 <= chunk_size:
        return buf + "\n\n" + piece
    out.append(buf)
    return piece


def _split_hard(text: str, chunk_size: int) -> List[str]:
    """Split a long block using progressively finer separators."""
    for sep in SEPARATORS:
        if sep in text:
            parts = text.split(sep)
            out: List[str] = []
            buf = ""
            for p in parts:
                candidate = f"{buf}{sep}{p}" if buf else p
                if len(candidate) <= chunk_size:
                    buf = candidate
                else:
                    if buf:
                        out.append(buf)
                    if len(p) > chunk_size:
                        out.extend(_hard_slice(p, chunk_size))
                        buf = ""
                    else:
                        buf = p
            if buf:
                out.append(buf)
            return out
    return _hard_slice(text, chunk_size)


def _hard_slice(text: str, chunk_size: int) -> List[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
