"""ChromaDB persistent vector store."""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.config import get_settings


class VectorStore:
    def __init__(self, persist_dir: str, collection_name: str) -> None:
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
        )
        # We pass embeddings explicitly, so no embedding_function needed.
        # Cosine distance in [0, 2]; normalized vectors give a "1 - cosine similarity" metric.
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Chroma collection '{collection_name}' ready at {persist_dir} (count={self.collection.count()})")

    def add(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        if not texts:
            return []
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        # Chroma metadata values must be str/int/float/bool. Coerce lists → comma strings.
        cleaned = [self._clean_meta(m) for m in metadatas]
        self.collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=cleaned)
        return ids

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=self._normalize_where(where),
            include=["documents", "metadatas", "distances"],
        )
        # Flatten Chroma's list-of-lists (batch of 1)
        return {
            "documents": result["documents"][0] if result.get("documents") else [],
            "metadatas": result["metadatas"][0] if result.get("metadatas") else [],
            "distances": result["distances"][0] if result.get("distances") else [],
            "ids": result["ids"][0] if result.get("ids") else [],
        }

    @staticmethod
    def _normalize_where(where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Chroma rejects empty/multi-key plain dicts. Drop or wrap them in $and."""
        if not where:
            return None
        # Already an operator dict ({"$and": [...]}, {"source": {"$eq": ...}}, etc.) — pass through.
        if any(k.startswith("$") for k in where):
            return where
        if len(where) == 1:
            return where  # single-key implicit-$eq form is still accepted
        return {"$and": [{k: v} for k, v in where.items()]}

    def count(self) -> int:
        return self.collection.count()

    def delete_by_doc_id(self, doc_id: str) -> int:
        # Chroma deletes chunks whose metadata.doc_id matches
        before = self.collection.count()
        self.collection.delete(where={"doc_id": doc_id})
        return before - self.collection.count()

    @staticmethod
    def _clean_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in meta.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                out[k] = v
            elif isinstance(v, list):
                out[k] = ", ".join(str(x) for x in v)
            else:
                out[k] = str(v)
        return out


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    s = get_settings()
    return VectorStore(persist_dir=s.chroma_dir, collection_name=s.chroma_collection)
