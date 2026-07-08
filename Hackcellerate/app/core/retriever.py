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
) -> List[RetrievedChunk]:
    """Retrieve, sort by best distance, keep those <= threshold, cap to final_k."""
    s = get_settings()
    top_k = top_k or s.rag_top_k
    final_k = final_k or s.rag_final_k
    threshold = distance_threshold if distance_threshold is not None else s.rag_distance_threshold

    embedder = get_embedding_model()
    store = get_vector_store()

    if store.count() == 0:
        logger.info("Vector store is empty — skipping retrieval.")
        return []

    q_vec = embedder.embed_one(query)
    res = store.query(query_embedding=q_vec, top_k=top_k, where=where)

    chunks: List[RetrievedChunk] = []
    for cid, doc, meta, dist in zip(res["ids"], res["documents"], res["metadatas"], res["distances"]):
        chunks.append(RetrievedChunk(chunk_id=cid, text=doc, metadata=meta or {}, distance=float(dist)))

    # Sort ascending by distance (best first)
    chunks.sort(key=lambda c: c.distance)

    # Filter by threshold
    grounded = [c for c in chunks if c.distance <= threshold]

    logger.info(
        f"Retrieved {len(chunks)} chunks; {len(grounded)} within distance<={threshold}. "
        f"best_distance={chunks[0].distance:.3f}" if chunks else "no chunks"
    )

    return grounded[:final_k]
