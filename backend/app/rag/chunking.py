"""تقسیم متن به قطعات هم‌پوشان، آگاه به جمله و پاراگراف فارسی — بدون فریمورک."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.document_loader import Section

_SPACE_RE = re.compile(r"[ \t\u00a0\u200b\f\v]+")
_SENTENCE_RE = re.compile(r"[^.!?؟۔؛:\n]+[.!?؟۔؛:]?", re.UNICODE)
_BLANK_LINE_RE = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    page: int | None = None


@dataclass(frozen=True)
class _Unit:
    text: str
    starts_paragraph: bool


def normalize_text(text: str) -> str:
    """یکسان‌سازی فاصله‌ها/شکست خط بدون دست‌زدن به نیم‌فاصله (ZWNJ)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _paragraphs(text: str) -> list[str]:
    blocks = [block.strip() for block in _BLANK_LINE_RE.split(text) if block.strip()]
    if len(blocks) <= 1 and "\n" in text:
        blocks = [block.strip() for block in text.split("\n") if block.strip()]
    return blocks


def _split_sentences(paragraph: str) -> list[str]:
    sentences = [match.group(0).strip() for match in _SENTENCE_RE.finditer(paragraph)]
    return [sentence for sentence in sentences if sentence]


def _to_units(text: str) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in _paragraphs(text):
        sentences = _split_sentences(paragraph) or [paragraph]
        for position, sentence in enumerate(sentences):
            units.append(_Unit(text=sentence, starts_paragraph=position == 0))
    return units


def _render(units: list[_Unit]) -> str:
    parts: list[str] = []
    for position, unit in enumerate(units):
        if position == 0:
            parts.append(unit.text)
        elif unit.starts_paragraph:
            parts.append("\n\n" + unit.text)
        else:
            parts.append(" " + unit.text)
    return "".join(parts).strip()


def _measure(units: list[_Unit]) -> int:
    return len(_render(units))


def _hard_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """شکستن یک «جمله‌ی بسیار بلند» که از chunk_size بزرگ‌تر است."""
    step = max(chunk_size - chunk_overlap, 1)
    pieces: list[str] = []
    position = 0
    while position < len(text):
        piece = text[position : position + chunk_size].strip()
        if piece:
            pieces.append(piece)
        if position + chunk_size >= len(text):
            break
        position += step
    return pieces


def _overlap_tail(units: list[_Unit], overlap_chars: int, limit: int) -> list[_Unit]:
    """انتخاب جمله‌های انتهایی قبلی برای هم‌پوشانی، بدون عبور از سقف اندازه."""
    if overlap_chars <= 0 or limit <= 0 or not units:
        return []
    picked: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        extra = len(unit.text) + (1 if picked else 0)
        if total + extra > overlap_chars or total + extra > limit:
            break
        picked.insert(0, unit)
        total += extra
    return picked


def split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """پنجره‌ی لغزان روی مرز جمله؛ هر chunk حداکثر chunk_size کاراکتر دارد."""
    if chunk_size <= 0:
        raise ValueError("chunk_size باید مثبت باشد.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap باید بین ۰ و chunk_size باشد.")

    normalized = normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= chunk_size:
        return [normalized]

    units = _to_units(normalized)
    chunks: list[str] = []
    buffer: list[_Unit] = []

    for unit in units:
        if len(unit.text) > chunk_size:
            if buffer:
                chunks.append(_render(buffer))
                buffer = []
            chunks.extend(_hard_split(unit.text, chunk_size, chunk_overlap))
            continue

        if buffer and _measure(buffer) + 1 + len(unit.text) > chunk_size:
            chunks.append(_render(buffer))
            buffer = _overlap_tail(buffer, chunk_overlap, chunk_size - len(unit.text) - 1)
        buffer.append(unit)

    if buffer:
        chunks.append(_render(buffer))

    return [chunk for chunk in chunks if chunk]


def chunk_sections(
    sections: list[Section],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """تبدیل بخش‌های سند (مثلاً صفحه‌های PDF) به قطعات شماره‌دار."""
    chunks: list[Chunk] = []
    for section in sections:
        for piece in split_text(section.text, chunk_size, chunk_overlap):
            chunks.append(Chunk(text=piece, index=len(chunks), page=section.page))
    return chunks
