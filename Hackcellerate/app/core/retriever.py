"""Retriever: embeds a query, pulls top-k chunks, filters by distance threshold."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from loguru import logger

from app.config import get_settings
from app.core.embeddings import get_embedding_model
from app.core.vector_store import get_vector_store


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: Dict[str, Any]
    distance: float

    @property
    def similarity(self) -> float:
        # Chroma cosine "distance" = 1 - cosine_similarity for normalized vectors
        return max(0.0, 1.0 - self.distance)


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    final_k: Optional[int] = None,
    distance_threshold: Optional[float] = None,
    where: Optional[Dict[str, Any]] = None,
    unique_docs: bool = False,
) -> List[RetrievedChunk]:
    """Retrieve, sort by best distance, keep those <= threshold, cap to final_k.

    If `unique_docs=True`, keep only the best-scoring chunk per source document
    (by `doc_id` in metadata, falling back to `chunk_id`). Useful for list-style
    queries where the user wants variety of documents rather than depth in one.
    """
    s = get_settings()
    top_k = top_k or s.rag_top_k
    final_k = final_k or s.rag_final_k
    threshold = distance_threshold if distance_threshold is not None else s.rag_distance_threshold

    embedder = get_embedding_model()
    store = get_vector_store()

    if store.count() == 0:
        logger.info("Vector store is empty — skipping retrieval.")
        return []

    # When deduplicating by document, pull a larger raw set so we still have
    # enough distinct documents after collapsing chunk-per-doc duplicates.
    fetch_k = top_k * 4 if unique_docs else top_k
    q_vec = embedder.embed_one(query)
    res = store.query(query_embedding=q_vec, top_k=fetch_k, where=where)

    chunks: List[RetrievedChunk] = []
    for cid, doc, meta, dist in zip(res["ids"], res["documents"], res["metadatas"], res["distances"]):
        chunks.append(RetrievedChunk(chunk_id=cid, text=doc, metadata=meta or {}, distance=float(dist)))

    # Sort ascending by distance (best first)
    chunks.sort(key=lambda c: c.distance)

    # Optional per-document dedup: keep only the best chunk per doc_id.
    if unique_docs:
        seen: set[str] = set()
        deduped: List[RetrievedChunk] = []
        for c in chunks:
            key = str((c.metadata or {}).get("doc_id") or c.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        chunks = deduped

    # Filter by threshold
    grounded = [c for c in chunks if c.distance <= threshold]

    logger.info(
        f"Retrieved {len(chunks)} chunks; {len(grounded)} within distance<={threshold}. "
        f"best_distance={chunks[0].distance:.3f} unique_docs={unique_docs}"
        if chunks else "no chunks"
    )

    return grounded[:final_k]
