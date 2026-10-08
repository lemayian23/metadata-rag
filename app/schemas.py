from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MetadataFilter(BaseModel):
    category: str | None = None
    author: str | None = None
    location: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    content: str
    source: str | None = None
    title: str | None = None
    author: str | None = None
    category: str | None = None
    location: str | None = None
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class IngestResponse(BaseModel):
    document_id: UUID
    chunks_created: int


class ImageIngestRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded image bytes")
    caption_hint: str | None = Field(
        None, description="Optional hint for the captioner"
    )
    source: str | None = None
    title: str | None = None
    author: str | None = None
    category: str | None = None
    location: str | None = None
    published_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ImageIngestResponse(BaseModel):
    document_id: UUID
    chunk_id: UUID
    modality: str
    caption: str


class QueryRequest(BaseModel):
    query: str
    filters: MetadataFilter | None = None
    top_k: int | None = None
    answer: bool = True
    extract_filters: bool = False
    rerank: bool = True
    rerank_candidates: int | None = None
    modality: str | None = None
    search_mode: str | None = None


class Citation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str | None
    source: str | None
    content: str
    modality: str | None = None
    score: float | None = None
    rerank_score: float | None = None
    rrf_score: float | None = None
    vector_rank: int | None = None
    keyword_rank: int | None = None
    keyword_score: float | None = None


class QueryResponse(BaseModel):
    answer: str | None
    citations: list[Citation]
    used_filters: MetadataFilter | None = None


class SupportInfo(BaseModel):
    supported: bool = True
    unsupported_claims: list[str] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str
    force_mode: str | None = None
    corrective: bool = True
    self_rag: bool = True
    search_mode: str | None = None


class AskResponse(BaseModel):
    mode: str
    source: str | None = None
    answer: str | None = None
    needed_retrieval: bool = True
    support: SupportInfo | None = None
    sql: str | None = None
    sql_rows: list[dict[str, Any]] = Field(default_factory=list)
    sql_error: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    corrective_trace: list[str] = Field(default_factory=list)


class AgentRequest(BaseModel):
    question: str
    max_steps: int = 6


class AgentResponse(BaseModel):
    answer: str
    evidence_count: int = 0
    steps: list[dict[str, Any]] = Field(default_factory=list)