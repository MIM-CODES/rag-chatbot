"""اندپوینت سلامت سرویس: ChromaDB، مدل‌ها و تنظیمات ناقص."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.models.schemas import HealthResponse
from app.runtime import get_components

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    components = get_components(request)
    settings = components.settings
    diagnostics: list[str] = []

    chroma_ok = True
    chunk_count = 0
    try:
        components.store.heartbeat()
        chunk_count = components.store.count()
    except Exception as exc:
        chroma_ok = False
        logger.exception("ChromaDB در دسترس نیست.")
        diagnostics.append(f"ChromaDB در دسترس نیست: {exc}")

    llm_reachable = await components.llm.check()
    if not llm_reachable:
        diagnostics.append(
            f"سرویس مدل زبانی ({settings.llm_base_url}) پاسخ نداد؛ "
            "بررسی کنید Ollama در حال اجراست و مدل دانلود شده است."
        )

    for name in settings.missing_settings:
        diagnostics.append(
            f"متغیر {name} در backend/.env تنظیم نشده است؛ تا مقداردهی نشود "
            "ایندکس‌گذاری و پاسخ‌دهی کار نمی‌کند."
        )

    if components.store.mismatch_reason:
        diagnostics.append(components.store.mismatch_reason)

    status = "ok" if not diagnostics else "degraded"

    return HealthResponse(
        status=status,
        chunk_count=chunk_count,
        document_count=components.registry.count(),
        llm_model=settings.llm_model,
        embedding_model=settings.embedding_model,
        llm_reachable=llm_reachable,
        chroma_ok=chroma_ok,
        diagnostics=diagnostics,
    )
