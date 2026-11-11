"""مدل‌های Pydantic برای درخواست/پاسخ API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Source(BaseModel):
    chunk_id: str
    doc_id: str
    filename: str
    page: int | None = None
    chunk_index: int
    score: float
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    conversation_id: str
    model: str


class IngestResult(BaseModel):
    filename: str
    doc_id: str | None = None
    status: Literal["indexed", "failed"]
    chunks: int = 0
    pages: int | None = None
    error: str | None = None
    warning: str | None = None


class IngestResponse(BaseModel):
    results: list[IngestResult]


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunks: int
    pages: int | None = None
    size_bytes: int
    indexed_at: str
    embedding_model: str
    warning: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    chunk_count: int
    document_count: int
    llm_model: str
    embedding_model: str
    llm_reachable: bool
    chroma_ok: bool
    diagnostics: list[str]


class ErrorResponse(BaseModel):
    detail: str
