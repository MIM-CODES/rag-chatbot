"""بارگذاری اسناد سازمانی (PDF/DOCX/TXT/Markdown) به متن قابل ایندکس."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".docx", ".txt", ".md", ".markdown"}
TEXT_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp1256", "latin-1")

_SPACE_RE = re.compile(r"[ \t\u00a0\u200b\f\v]+")


class DocumentLoadError(Exception):
    """خطای قابل نمایش به کاربر هنگام خواندن سند."""


class UnsupportedFileType(DocumentLoadError):
    """پسوند فایل پشتیبانی نمی‌شود."""


@dataclass(frozen=True)
class Section:
    """یک قطعه‌ی متنی از سند؛ page برای فایل‌های صفحه‌دار (PDF) پر می‌شود."""

    text: str
    page: int | None = None


@dataclass
class LoadedDocument:
    sections: list[Section] = field(default_factory=list)
    page_count: int | None = None
    warning: str | None = None

    @property
    def text_length(self) -> int:
        return sum(len(section.text) for section in self.sections)


def _clean_line(line: str) -> str:
    return _SPACE_RE.sub(" ", line).replace("\u200b", "").strip()


def _normalize(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_clean_line(line) for line in normalized.split("\n")]
    result = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def _decode_text(data: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentLoadError("انکودینگ فایل متنی شناسایی نشد (UTF-8 یا Windows-1256 لازم است).")


def _load_pdf(path: Path) -> LoadedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - وابستگی همیشه نصب است
        raise DocumentLoadError("کتابخانه‌ی pypdf نصب نیست.") from exc

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise DocumentLoadError("فایل PDF رمزگذاری شده است و قابل خواندن نیست.") from exc
        sections: list[Section] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                raw = page.extract_text() or ""
            except Exception:  # صفحه‌ی خراب نباید کل سند را از کار بیندازد
                logger.warning("استخراج متن صفحه %s ناموفق بود: %s", page_number, path.name)
                raw = ""
            text = _normalize(raw)
            if text:
                sections.append(Section(text=text, page=page_number))
        loaded = LoadedDocument(sections=sections, page_count=len(reader.pages))
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError(f"خواندن PDF ناموفق بود: {exc}") from exc

    if not sections:
        loaded.warning = (
            "هیچ متنی از این PDF استخراج نشد؛ احتمالاً اسکن‌شده (تصویری) است. "
            "OCR در این نسخه پشتیبانی نمی‌شود."
        )
    return loaded


def _load_docx(path: Path) -> LoadedDocument:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise DocumentLoadError("کتابخانه‌ی python-docx نصب نیست.") from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise DocumentLoadError(f"خواندن DOCX ناموفق بود: {exc}") from exc

    blocks: list[str] = []
    for paragraph in document.paragraphs:
        text = _normalize(paragraph.text)
        if text:
            blocks.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [_normalize(cell.text) for cell in row.cells]
            line = " | ".join(cell for cell in cells if cell)
            if line:
                blocks.append(line)

    text = "\n\n".join(blocks).strip()
    loaded = LoadedDocument(sections=[Section(text=text)] if text else [])
    if not loaded.sections:
        loaded.warning = "این فایل DOCX متن قابل استخراجی ندارد."
    return loaded


def _load_text(path: Path) -> LoadedDocument:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DocumentLoadError(f"خواندن فایل ناموفق بود: {exc}") from exc
    text = _normalize(_decode_text(data))
    loaded = LoadedDocument(sections=[Section(text=text)] if text else [])
    if not loaded.sections:
        loaded.warning = "فایل متنی خالی است."
    return loaded


def load_document(path: Path | str) -> LoadedDocument:
    """خواندن سند بر اساس پسوند فایل و برگرداندن متن + متادیتای صفحه."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(
            f"پسوند «{suffix or 'نامشخص'}» پشتیبانی نمی‌شود. "
            f"فرمت‌های مجاز: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if not file_path.exists():
        raise DocumentLoadError("فایل سند پیدا نشد.")

    if suffix == ".pdf":
        return _load_pdf(file_path)
    if suffix == ".docx":
        return _load_docx(file_path)
    return _load_text(file_path)
