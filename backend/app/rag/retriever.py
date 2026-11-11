"""جست‌وجوی معنایی در ChromaDB + فیلتر آستانه‌ی شباهت."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.models.schemas import Source
from app.rag.embeddings import Embedder
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 420


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    doc_id: str
    filename: str
    page: int | None
    chunk_index: int
    score: float


def to_source(chunk: RetrievedChunk, snippet_chars: int = SNIPPET_CHARS) -> Source:
    snippet = chunk.text.strip()
    if len(snippet) > snippet_chars:
        snippet = snippet[:snippet_chars].rstrip() + "…"
    return Source(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        filename=chunk.filename,
        page=chunk.page,
        chunk_index=chunk.chunk_index,
        score=round(chunk.score, 4),
        snippet=snippet,
    )


async def retrieve(
    question: str,
    embedder: Embedder,
    store: VectorStore,
    *,
    top_k: int,
    threshold: float,
) -> list[RetrievedChunk]:
    """سؤال را embedding می‌کند و مرتبط‌ترین قطعات بالای آستانه را برمی‌گرداند."""
    question = question.strip()
    if not question:
        return []

    embedding = await embedder.embed_query(question)
    matches = store.query(embedding, top_k=top_k)

    retrieved: list[RetrievedChunk] = []
    for match in matches:
        # فاصله‌ی کسینوسی = ۱ - شباهت کسینوسی
        score = 1.0 - float(match["distance"])
        if score < threshold:
            continue
        metadata = match["metadata"]
        page = metadata.get("page")
        retrieved.append(
            RetrievedChunk(
                chunk_id=match["chunk_id"],
                text=match["text"],
                doc_id=str(metadata.get("doc_id", "")),
                filename=str(metadata.get("filename", "سند")),
                page=int(page) if page is not None else None,
                chunk_index=int(metadata.get("chunk_index", 0)),
                score=score,
            )
        )

    retrieved.sort(key=lambda item: item.score, reverse=True)
    if not retrieved:
        logger.info("هیچ قطعه‌ای بالای آستانه‌ی شباهت پیدا نشد (threshold=%.2f).", threshold)
    return retrieved
