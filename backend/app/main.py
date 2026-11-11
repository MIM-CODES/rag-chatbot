"""نقطه‌ی ورود FastAPI: تنظیمات، CORS، مسیرها و سرو کردن فرانت‌اند."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_chat, routes_health, routes_ingest
from app.config import FRONTEND_DIR, Settings, get_settings
from app.llm.client import LLMError
from app.rag.embeddings import EmbeddingError
from app.rag.vector_store import EmbeddingModelMismatch
from app.runtime import Components, build_components

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    components: Components | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    logging.basicConfig(
        level=getattr(logging, resolved_settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        built = components or build_components(resolved_settings)
        app.state.components = built

        if built.settings.missing_settings:
            logger.warning(
                "این متغیرها در backend/.env تنظیم نشده‌اند: %s",
                ", ".join(built.settings.missing_settings),
            )
        if built.store.mismatch_reason:
            logger.error(built.store.mismatch_reason)
        logger.info(
            "آماده‌به‌کار: collection=%s، قطعات=%s، اسناد=%s، مدل چت=%s، مدل embedding=%s",
            built.settings.chroma_collection_name,
            built.store.count(),
            built.registry.count(),
            built.settings.llm_model or "(تنظیم نشده)",
            built.settings.embedding_model or "(تنظیم نشده)",
        )
        yield

    app = FastAPI(
        title="چت‌بات سازمانی RAG",
        description="RAG دستی بدون فریمورک: ChromaDB + FastAPI + مدل زبانی سازگار با OpenAI",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LLMError)
    async def _llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(EmbeddingError)
    async def _embedding_error_handler(_: Request, exc: EmbeddingError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(EmbeddingModelMismatch)
    async def _mismatch_handler(_: Request, exc: EmbeddingModelMismatch) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(routes_health.router, prefix="/api")
    app.include_router(routes_ingest.router, prefix="/api")
    app.include_router(routes_chat.router, prefix="/api")

    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    else:  # pragma: no cover
        logger.warning("پوشه‌ی frontend پیدا نشد: %s", FRONTEND_DIR)

    return app


app = create_app()
