"""دفتر اسناد ایندکس‌شده (manifest روی دیسک) برای فهرست/حذف سریع و پایدار."""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DocumentRecord:
    doc_id: str
    filename: str
    stored_filename: str
    chunks: int
    pages: int | None
    size_bytes: int
    indexed_at: str
    embedding_model: str
    warning: str | None = None


class DocumentRegistry:
    """نگهداری متادیتای اسناد در یک فایل JSON با نوشتن اتمیک."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._records: dict[str, DocumentRecord] = {}
        self._load()

    # ---------- داخلی ----------

    def _load(self) -> None:
        if not self._path.exists():
            self._records = {}
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            documents = payload.get("documents", {})
            self._records = {
                doc_id: DocumentRecord(**data) for doc_id, data in documents.items()
            }
        except Exception:
            logger.exception("خواندن manifest اسناد ناموفق بود؛ فهرست خالی در نظر گرفته شد.")
            self._records = {}

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"documents": {doc_id: asdict(rec) for doc_id, rec in self._records.items()}}
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._path)

    # ---------- عمومی ----------

    def list(self) -> list[DocumentRecord]:
        with self._lock:
            records = list(self._records.values())
        return sorted(records, key=lambda rec: rec.indexed_at, reverse=True)

    def get(self, doc_id: str) -> DocumentRecord | None:
        with self._lock:
            return self._records.get(doc_id)

    def upsert(self, record: DocumentRecord) -> None:
        with self._lock:
            self._records[record.doc_id] = record
            self._flush()

    def remove(self, doc_id: str) -> DocumentRecord | None:
        with self._lock:
            record = self._records.pop(doc_id, None)
            if record is not None:
                self._flush()
            return record

    def count(self) -> int:
        with self._lock:
            return len(self._records)
