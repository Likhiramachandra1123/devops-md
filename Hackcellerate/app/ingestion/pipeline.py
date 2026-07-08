"""High-level ingestion pipeline: text → chunks → embeddings → vector store."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.config import get_settings
from app.core.embeddings import get_embedding_model
from app.core.vector_store import get_vector_store
from app.ingestion.chunker import chunk_text
from app.ingestion.loaders import load_file, load_url


def _make_doc_id(source: str, title: str, url: Optional[str], text: str) -> str:
    h = hashlib.sha256()
    h.update((source + "|" + title + "|" + (url or "") + "|" + text[:512]).encode("utf-8"))
    return h.hexdigest()[:24]


def ingest_text(
    title: str,
    text: str,
    source: str,
    url: Optional[str] = None,
    doc_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int]:
    """Chunk, embed, and store one document. Returns (doc_id, chunk_count)."""
    s = get_settings()
    text = (text or "").strip()
    if not text:
        return ("", 0)

    doc_id = _make_doc_id(source, title, url, text)
    chunks = chunk_text(text, chunk_size=s.chunk_size, overlap=s.chunk_overlap)
    if not chunks:
        return (doc_id, 0)

    texts = [c.text for c in chunks]
    embedder = get_embedding_model()
    embeddings = embedder.embed(texts)

    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []
    for c in chunks:
        meta: Dict[str, Any] = {
            "doc_id": doc_id,
            "chunk_index": c.index,
            "title": title,
            "source": source,
        }
        if url:
            meta["url"] = url
        if doc_type:
            meta["doc_type"] = doc_type
        if tags:
            meta["tags"] = tags
        if extra_meta:
            meta.update(extra_meta)
        metadatas.append(meta)
        ids.append(f"{doc_id}:{c.index}")

    store = get_vector_store()
    store.add(texts=texts, embeddings=embeddings, metadatas=metadatas, ids=ids)
    logger.info(f"Ingested doc_id={doc_id} title='{title[:60]}' chunks={len(chunks)} source={source}")
    return (doc_id, len(chunks))


def ingest_file(
    path: Path,
    source: str = "upload",
    doc_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[str, int]:
    title, text = load_file(path)
    return ingest_text(title=title, text=text, source=source, doc_type=doc_type, tags=tags, url=None)


async def ingest_url(
    url: str,
    source: str = "web",
    doc_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[str, int]:
    title, text = await load_url(url)
    return ingest_text(title=title, text=text, source=source, url=url, doc_type=doc_type, tags=tags)
