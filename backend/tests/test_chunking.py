import pytest

from app.rag.chunking import chunk_sections, split_text
from app.services.document_loader import Section


def test_short_text_stays_one_chunk():
    assert split_text("یک جمله‌ی کوتاه.", 800, 120) == ["یک جمله‌ی کوتاه."]


def test_empty_text_returns_nothing():
    assert split_text("   \n\n  ", 800, 120) == []


def test_chunks_never_exceed_size_and_all_content_kept():
    text = "این یک جمله‌ی آزمایشی برای تست تقسیم‌بندی است. " * 120
    chunks = split_text(text, 300, 60)

    assert len(chunks) > 1
    assert all(len(chunk) <= 300 for chunk in chunks)
    # هر جمله باید حداقل در یکی از قطعات حاضر باشد
    for sentence in text.split(". ")[:10]:
        assert any(sentence.strip()[:20] in chunk for chunk in chunks)


def test_persian_sentence_boundaries_preserved():
    text = "سیاست مرخصی چیست؟ باید فرم پر شود. مدیر تأیید می‌کند! سپس ثبت می‌شود."
    chunks = split_text(text, 40, 10)

    assert all(len(chunk) <= 40 for chunk in chunks)
    joined = " ".join(chunks)
    for punctuation in ("؟", "!", "."):
        assert punctuation in joined


def test_very_long_sentence_is_hard_split():
    text = "الف" * 2000
    chunks = split_text(text, 200, 20)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert sum(len(chunk) for chunk in chunks) > len(text)  # هم‌پوشانی دارد


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        split_text("متن", 100, 100)
    with pytest.raises(ValueError):
        split_text("متن", 100, -1)


def test_chunk_sections_keeps_page_and_global_index():
    sections = [
        Section("متن صفحه‌ی اول است. " * 20, page=1),
        Section("متن صفحه‌ی دوم است. " * 20, page=2),
    ]
    chunks = chunk_sections(sections, 120, 20)

    assert len(chunks) > 2
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.page for chunk in chunks} == {1, 2}


def test_overlap_produces_shared_context():
    sentences = [f"جمله شماره {index} درباره‌ی سیاست سازمان است." for index in range(40)]
    text = " ".join(sentences)
    chunks = split_text(text, 200, 80)

    shared = False
    for previous, current in zip(chunks, chunks[1:]):
        tail = previous[-25:].strip()
        if tail and tail in current:
            shared = True
            break
    assert shared, "هیچ هم‌پوشانی‌ای بین قطعات متوالی پیدا نشد."
