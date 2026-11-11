"""اندپوینت‌های چت: پاسخ کامل JSON و پاسخ جریانی با Server-Sent Events."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.llm.client import LLMError
from app.models.schemas import ChatRequest, ChatResponse, Source
from app.rag.embeddings import EmbeddingError
from app.rag.prompt_builder import NO_CONTEXT_ANSWER, build_messages
from app.rag.retriever import retrieve, to_source
from app.runtime import Components, get_components

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _preflight(components: Components) -> None:
    if components.store.mismatch_reason:
        raise HTTPException(status_code=409, detail=components.store.mismatch_reason)
    if not components.settings.embedding_model:
        raise HTTPException(
            status_code=409,
            detail="EMBEDDING_MODEL در backend/.env تنظیم نشده است.",
        )
    if not components.settings.llm_model:
        raise HTTPException(status_code=409, detail="LLM_MODEL در backend/.env تنظیم نشده است.")


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _prepare(
    components: Components,
    payload: ChatRequest,
    conversation_id: str,
) -> tuple[list[Source], list[dict[str, str]] | None]:
    """بازیابی منابع و ساخت پیام‌ها؛ اگر منبعی نبود خروجی None برمی‌گردد."""
    settings = components.settings
    top_k = payload.top_k or settings.retrieval_top_k
    chunks = await retrieve(
        payload.message,
        components.embedder,
        components.store,
        top_k=top_k,
        threshold=settings.similarity_threshold,
    )
    if not chunks:
        return [], None

    messages, used = build_messages(
        payload.message,
        chunks,
        payload.history,
        context_max_chars=settings.context_max_chars,
        history_max_turns=settings.history_max_turns,
    )
    return [to_source(chunk) for chunk in used], messages


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    components = get_components(request)
    _preflight(components)
    conversation_id = payload.conversation_id or uuid4().hex[:12]

    sources, messages = await _prepare(components, payload, conversation_id)
    if not messages:
        return ChatResponse(
            answer=NO_CONTEXT_ANSWER,
            sources=[],
            conversation_id=conversation_id,
            model=components.settings.llm_model,
        )

    answer = await components.llm.complete(messages)
    return ChatResponse(
        answer=answer,
        sources=sources,
        conversation_id=conversation_id,
        model=components.settings.llm_model,
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    components = get_components(request)
    _preflight(components)
    conversation_id = payload.conversation_id or uuid4().hex[:12]

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("open", {"conversation_id": conversation_id})
        try:
            sources, messages = await _prepare(components, payload, conversation_id)
            if not messages:
                yield _sse("sources", {"sources": []})
                yield _sse("token", {"delta": NO_CONTEXT_ANSWER})
                yield _sse("done", {"conversation_id": conversation_id, "stopped": False})
                return

            yield _sse("sources", {"sources": [source.model_dump() for source in sources]})
            async for delta in components.llm.stream(messages):
                yield _sse("token", {"delta": delta})
            yield _sse("done", {"conversation_id": conversation_id, "stopped": False})
        except (EmbeddingError, LLMError) as exc:
            logger.warning("خطا در جریان پاسخ: %s", exc)
            yield _sse("error", {"message": str(exc), "status_code": exc.status_code})
        except asyncio.CancelledError:
            logger.info("کلاینت اتصال را بست؛ تولید پاسخ متوقف شد.")
            raise
        except Exception:
            logger.exception("خطای غیرمنتظره در جریان پاسخ.")
            yield _sse("error", {"message": "خطای غیرمنتظره در پردازش درخواست رخ داد."})

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)
