"""Pydantic schemas for API contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------- Chat ----------

class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Existing session id. If omitted a new one is created.")
    message: str = Field(..., min_length=1, description="User's natural-language regulatory query.")
    use_rag: bool = Field(True, description="Retrieve internal knowledge base context before calling Claude.")
    filters: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional metadata filters, e.g. {'source': 'openFDA', 'doc_type': 'label'}",
    )
    top_k: Optional[int] = Field(None, ge=1, le=1000)
    model: Optional[str] = Field(None, description="Override the default Claude model for this call.")


class Citation(BaseModel):
    index: int
    title: str
    source: str
    url: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    distance: float
    snippet: str


SourceType = Literal["knowledge_base", "uploaded_document", "general_knowledge", "none"]


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    summary: str
    citations: List[Citation]
    used_rag: bool
    grounded: bool = Field(..., description="True if answer was grounded in retrieved context above the relevance threshold.")
    source_type: SourceType = Field("none", description="Where the answer came from.")
    source_info: Dict[str, Any] = Field(default_factory=dict, description="Extra info about the source (e.g. filename).")
    model: str
    usage: Dict[str, int] = Field(default_factory=dict)


# ---------- Structured search (table view) ----------

class SearchResult(BaseModel):
    index: int
    title: str
    source: str
    url: Optional[str] = None
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    distance: float
    score: float = Field(..., description="Convenience: 1 - distance, clipped to [0, 1].")
    snippet: str
    text: str = Field("", description="Full chunk text (used for the expanded-row view).")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    session_id: str
    query: str
    results: List[SearchResult]
    total: int
    summary: Optional[str] = None


# ---------- Sessions ----------

class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class SessionInfo(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    title: Optional[str] = None


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[Message]


# ---------- Ingestion ----------

class IngestUrlRequest(BaseModel):
    urls: List[str]
    source: str = Field("web", description="Logical source tag, e.g. 'openFDA', 'ClinicalTrials'.")
    doc_type: Optional[str] = None
    tags: Optional[List[str]] = None


class IngestTextRequest(BaseModel):
    title: str
    text: str
    source: str = "manual"
    doc_type: Optional[str] = None
    url: Optional[str] = None
    tags: Optional[List[str]] = None


class IngestResponse(BaseModel):
    ingested_documents: int
    ingested_chunks: int
    doc_ids: List[str]


class ConnectorIngestRequest(BaseModel):
    query: str = Field(..., description="Search term, e.g. drug name or condition.")
    limit: int = Field(20, ge=1, le=200)


class SourceIngestRequest(BaseModel):
    type: str = Field(..., description="Connector type: 'sql', 'mongo', or 's3'.")
    config: Dict[str, Any] = Field(..., description="Connector-specific config; see connector docstring.")
    max_records: int = Field(100, ge=1, le=100_000, description="Cap total records ingested in this run.")
    tags: Optional[List[str]] = Field(None, description="Extra tags merged into every ingested record.")


class SourceIngestResponse(BaseModel):
    total_records_seen: int
    total_records_ingested: int
    total_chunks: int
    doc_ids: List[str]
    errors: List[str] = Field(default_factory=list)


# ---------- Health ----------

class HealthResponse(BaseModel):
    status: str
    version: str
    model: str
    embedding_model: str
    vector_store_count: int


# ---------- Models catalog ----------

class ModelInfo(BaseModel):
    id: str = Field(..., description="Anthropic model id to pass to the API.")
    display_name: str = Field(..., description="Human-friendly name.")
    family: str = Field("claude", description="Model family: claude / haiku / sonnet / opus.")
    context_window: int = Field(0, description="Max input tokens the model accepts.")
    input_price_per_mtok: Optional[float] = Field(None, description="USD per 1M input tokens (list price).")
    output_price_per_mtok: Optional[float] = Field(None, description="USD per 1M output tokens (list price).")
    created_at: Optional[str] = None
    is_default: bool = False
    pricing_known: bool = True
    description: Optional[str] = None


class ModelsResponse(BaseModel):
    models: List[ModelInfo]
    default_model: str
    source: str = Field(..., description="'api' if fetched from Anthropic, 'static' if fallback.")

