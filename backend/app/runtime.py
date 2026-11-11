"""ساخت و نگه‌داری اجزای مشترک برنامه (composition root)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.llm.client import LLMClient
from app.rag.embeddings import Embedder
from app.rag.vector_store import VectorStore
from app.services.registry import DocumentRegistry


@dataclass
class Components:
    settings: Settings
    embedder: Embedder
    store: VectorStore
    llm: LLMClient
    registry: DocumentRegistry


def build_components(settings: Settings) -> Components:
    settings.ensure_directories()
    registry_path = settings.raw_documents_dir.parent / "doc_registry.json"
    return Components(
        settings=settings,
        embedder=Embedder(settings),
        store=VectorStore(
            persist_dir=settings.chroma_persist_dir,
            collection_name=settings.chroma_collection_name,
            embedding_model=settings.embedding_model,
        ),
        llm=LLMClient(settings),
        registry=DocumentRegistry(registry_path),
    )


def get_components(request: Request) -> Components:
    components = getattr(request.app.state, "components", None)
    if components is None:  # pragma: no cover - فقط اگر lifespan اجرا نشده باشد
        raise RuntimeError("اجزای برنامه مقداردهی نشده‌اند.")
    return components
