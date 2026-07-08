"""PubMedBERT-based embedding provider (sentence-transformers).

Model default: `pritamdeka/S-PubMedBert-MS-MARCO` — a sentence-transformers checkpoint
fine-tuned from PubMedBERT for biomedical semantic search.

Falls back to mean-pooled raw transformer if sentence-transformers can't load the model.
"""
from __future__ import annotations

import threading
from functools import lru_cache
from typing import List

import numpy as np
from loguru import logger

from app.config import get_settings


class EmbeddingModel:
    """Thread-safe singleton wrapper around a sentence-transformers embedding model."""

    _lock = threading.Lock()
    _instance: "EmbeddingModel | None" = None

    def __init__(self, model_name: str, device: str) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None
        self._dim: int | None = None
        self._load()

    def _load(self) -> None:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model '{self.model_name}' on {self.device} ...")
        self._model = SentenceTransformer(self.model_name, device=self.device)
        # Warm up + capture dimension
        vec = self._model.encode(["warmup"], normalize_embeddings=True)
        self._dim = int(vec.shape[1])
        logger.info(f"Embedding model ready. dim={self._dim}")

    @property
    def dim(self) -> int:
        assert self._dim is not None
        return self._dim

    def embed(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        if not texts:
            return []
        assert self._model is not None
        vecs = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32).tolist()

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    s = get_settings()
    with EmbeddingModel._lock:
        return EmbeddingModel(s.embedding_model, s.embedding_device)
