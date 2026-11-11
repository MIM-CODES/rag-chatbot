"""لایه‌ی نازک روی ChromaDB (PersistentClient) بدون هیچ انتزاع فریمورکی."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.rag.chunking import Chunk

logger = logging.getLogger(__name__)

ADD_BATCH_SIZE = 100


class EmbeddingModelMismatch(Exception):
    """مدل embedding تغییر کرده اما collection با بردارهای مدل قبلی پر است."""


class VectorStore:
    def __init__(
        self,
        persist_dir: Path | str,
        collection_name: str,
        embedding_model: str,
    ) -> None:
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name
        self._embedding_model = embedding_model
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": embedding_model or "unset"},
        )
        self.mismatch_reason = self._detect_mismatch()

    # ---------- کمکی ----------

    def _detect_mismatch(self) -> str | None:
        stored = (self._collection.metadata or {}).get("embedding_model")
        configured = self._embedding_model or "unset"
        if stored and stored != configured:
            return (
                f"این مجموعه با مدل embedding «{stored}» ساخته شده اما تنظیمات فعلی «{configured}» است. "
                "برای جلوگیری از ناسازگاری بردارها، اسناد قبلی را حذف و دوباره ایندکس کنید "
                "(یا EMBEDDING_MODEL را به همان مقدار قبلی برگردانید)."
            )
        return None

    # ---------- نوشتن ----------

    def add_chunks(
        self,
        *,
        doc_id: str,
        filename: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        indexed_at: str,
    ) -> int:
        if self.mismatch_reason:
            raise EmbeddingModelMismatch(self.mismatch_reason)
        if len(chunks) != len(embeddings):
            raise ValueError("تعداد قطعات و بردارها برابر نیست.")

        for start in range(0, len(chunks), ADD_BATCH_SIZE):
            batch_chunks = chunks[start : start + ADD_BATCH_SIZE]
            batch_vectors = embeddings[start : start + ADD_BATCH_SIZE]
            ids = [f"{doc_id}:{chunk.index}" for chunk in batch_chunks]
            metadatas: list[dict[str, Any]] = []
            for chunk in batch_chunks:
                metadata: dict[str, Any] = {
                    "doc_id": doc_id,
                    "filename": filename,
                    "chunk_index": chunk.index,
                    "indexed_at": indexed_at,
                    "embedding_model": self._embedding_model,
                }
                if chunk.page is not None:
                    metadata["page"] = chunk.page
                metadatas.append(metadata)

            self._collection.add(
                ids=ids,
                documents=[chunk.text for chunk in batch_chunks],
                embeddings=batch_vectors,
                metadatas=metadatas,
            )
        return len(chunks)

    def delete_document(self, doc_id: str) -> None:
        self._collection.delete(where={"doc_id": doc_id})

    # ---------- خواندن ----------

    def query(self, embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        total = self.count()
        if total == 0 or top_k < 1:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        matches: list[dict[str, Any]] = []
        for position, chunk_id in enumerate(ids):
            metadata = metadatas[position] or {}
            matches.append(
                {
                    "chunk_id": chunk_id,
                    "text": documents[position] or "",
                    "metadata": metadata,
                    "distance": float(distances[position]),
                }
            )
        return matches

    def count(self) -> int:
        return self._collection.count()

    def heartbeat(self) -> int:
        return self._client.heartbeat()

    def reset_collection(self) -> None:
        """حذف کامل collection (برای تست/بازسازی)."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": self._embedding_model or "unset"},
        )
