"""Application configuration loaded from environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Claude
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    claude_model: str = Field("claude-3-5-haiku-latest", alias="CLAUDE_MODEL")
    claude_max_tokens: int = Field(1500, alias="CLAUDE_MAX_TOKENS")
    claude_temperature: float = Field(0.2, alias="CLAUDE_TEMPERATURE")

    # App
    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8000, alias="APP_PORT")
    app_env: str = Field("dev", alias="APP_ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    cors_origins: Annotated[List[str], NoDecode] = Field(default_factory=lambda: ["*"], alias="CORS_ORIGINS")

    # RAG
    embedding_model: str = Field("pritamdeka/S-PubMedBert-MS-MARCO", alias="EMBEDDING_MODEL")
    embedding_device: str = Field("cpu", alias="EMBEDDING_DEVICE")
    chroma_dir: str = Field("./data/chroma", alias="CHROMA_DIR")
    chroma_collection: str = Field("regview_docs", alias="CHROMA_COLLECTION")
    chunk_size: int = Field(800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(120, alias="CHUNK_OVERLAP")
    rag_top_k: int = Field(5, alias="RAG_TOP_K")
    rag_final_k: int = Field(3, alias="RAG_FINAL_K")
    rag_distance_threshold: float = Field(0.65, alias="RAG_DISTANCE_THRESHOLD")
    # Extra safety net: even if chunks pass the threshold, the TOP-1 chunk must be
    # at least this close or we abstain. Lower = stricter. 0 disables the check.
    # Disabled by default — set >0 in .env only if you want the extra floor.
    rag_top_distance_floor: float = Field(0.0, alias="RAG_TOP_DISTANCE_FLOOR")
    rag_strict: bool = Field(True, alias="RAG_STRICT")
    # When True (default), a question that is IN SCOPE for the knowledge base
    # topic (regulatory / drugs / devices / clinical trials / MedDRA) but whose
    # answer isn't found in ChromaDB is answered from Claude's general knowledge
    # with a clearly-labelled warning banner, instead of a hard refusal. Genuine
    # off-topic questions (sports, trivia, coding) are still refused.
    rag_allow_general_fallback: bool = Field(True, alias="RAG_ALLOW_GENERAL_FALLBACK")

    # Memory
    session_db_url: str = Field("sqlite+aiosqlite:///./data/sessions.db", alias="SESSION_DB_URL")
    max_history_messages: int = Field(50, alias="MAX_HISTORY_MESSAGES")

    # Data
    documents_dir: str = Field("./data/documents", alias="DOCUMENTS_DIR")

    # Uploads (chat /chat/upload endpoint)
    # Claude 3.5 Haiku has a 200K token context (~700K chars). Default 400K keeps a
    # safety margin for the system prompt + conversation history.
    upload_max_bytes: int = Field(30 * 1024 * 1024, alias="UPLOAD_MAX_BYTES")
    upload_max_doc_chars: int = Field(400_000, alias="UPLOAD_MAX_DOC_CHARS")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    def ensure_dirs(self) -> None:
        Path(self.chroma_dir).mkdir(parents=True, exist_ok=True)
        Path(self.documents_dir).mkdir(parents=True, exist_ok=True)
        Path("./data").mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()  # type: ignore[call-arg]
    s.ensure_dirs()
    return s
