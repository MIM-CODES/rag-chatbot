"""اندپوینت‌های ایندکس‌گذاری و مدیریت اسناد."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.models.schemas import DocumentInfo, IngestResponse, IngestResult
from app.rag.chunking import chunk_sections
from app.rag.embeddings import EmbeddingError
from app.rag.vector_store import EmbeddingModelMismatch
from app.runtime import Components, get_components
from app.services.document_loader import (
    SUPPORTED_EXTENSIONS,
    DocumentLoadError,
    load_document,
)
from app.services.registry import DocumentRecord

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_filename(raw: str | None) -> str:
    name = Path(raw or "document").name.strip().replace("\x00", "")
    return name or "document"


def _failed(filename: str, message: str, doc_id: str | None = None) -> IngestResult:
    return IngestResult(filename=filename, doc_id=doc_id, status="failed", error=message)


async def _ingest_one(components: Components, upload: UploadFile) -> IngestResult:
    settings = components.settings
    filename = _safe_filename(upload.filename)
    suffix = Path(filename).suffix.lower()

    try:
        if suffix not in SUPPORTED_EXTENSIONS:
            return _failed(
                filename,
                f"پسوند «{suffix or 'نامشخص'}» پشتیبانی نمی‌شود. "
                f"فرمت‌های مجاز: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )

        data = await upload.read()
        if not data:
            return _failed(filename, "فایل خالی است.")
        if len(data) > settings.max_upload_bytes:
            return _failed(filename, f"حجم فایل بیش از {settings.max_upload_mb} مگابایت است.")

        doc_id = uuid4().hex[:12]
        stored_filename = f"{doc_id}{suffix}"
        stored_path = settings.raw_documents_dir / stored_filename
        stored_path.write_bytes(data)

        try:
            loaded = load_document(stored_path)
            if not loaded.sections:
                raise DocumentLoadError(loaded.warning or "متنی برای ایندکس در این سند پیدا نشد.")

            chunks = chunk_sections(loaded.sections, settings.chunk_size, settings.chunk_overlap)
            if not chunks:
                raise DocumentLoadError("پس از تقسیم‌بندی، قطعه‌ی قابل ایندکسی باقی نماند.")

            embeddings = await components.embedder.embed_texts([chunk.text for chunk in chunks])
            indexed_at = _now()
            components.store.add_chunks(
                doc_id=doc_id,
                filename=filename,
                chunks=chunks,
                embeddings=embeddings,
                indexed_at=indexed_at,
            )
            components.registry.upsert(
                DocumentRecord(
                    doc_id=doc_id,
                    filename=filename,
                    stored_filename=stored_filename,
                    chunks=len(chunks),
                    pages=loaded.page_count,
                    size_bytes=len(data),
                    indexed_at=indexed_at,
                    embedding_model=settings.embedding_model,
                    warning=loaded.warning,
                )
            )
        except Exception:
            # پاک‌سازی نیم‌کاره‌ی ناموفق تا داده‌ی ناقص در پایگاه‌داده نماند
            try:
                components.store.delete_document(doc_id)
            except Exception:
                logger.warning("حذف قطعات نیم‌کاره‌ی سند %s ناموفق بود.", doc_id)
            stored_path.unlink(missing_ok=True)
            raise

        return IngestResult(
            filename=filename,
            doc_id=doc_id,
            status="indexed",
            chunks=len(chunks),
            pages=loaded.page_count,
            warning=loaded.warning,
        )
    except (DocumentLoadError, EmbeddingError, EmbeddingModelMismatch, ValueError) as exc:
        return _failed(filename, str(exc))
    except Exception:
        logger.exception("پردازش سند %s ناموفق بود.", filename)
        return _failed(filename, "خطای غیرمنتظره در پردازش سند رخ داد.")
    finally:
        await upload.close()


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: Request, files: list[UploadFile] = File(...)) -> IngestResponse:
    components = get_components(request)
    if components.store.mismatch_reason:
        raise HTTPException(status_code=409, detail=components.store.mismatch_reason)
    if not files:
        raise HTTPException(status_code=400, detail="هیچ فایلی ارسال نشده است.")

    results = [await _ingest_one(components, upload) for upload in files]
    return IngestResponse(results=results)


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(request: Request) -> list[DocumentInfo]:
    components = get_components(request)
    return [
        DocumentInfo(
            doc_id=record.doc_id,
            filename=record.filename,
            chunks=record.chunks,
            pages=record.pages,
            size_bytes=record.size_bytes,
            indexed_at=record.indexed_at,
            embedding_model=record.embedding_model,
            warning=record.warning,
        )
        for record in components.registry.list()
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request) -> dict[str, str]:
    components = get_components(request)
    record = components.registry.get(doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail="سندی با این شناسه پیدا نشد.")

    components.store.delete_document(doc_id)
    (components.settings.raw_documents_dir / record.stored_filename).unlink(missing_ok=True)
    components.registry.remove(doc_id)
    return {"status": "deleted", "doc_id": doc_id, "filename": record.filename}
