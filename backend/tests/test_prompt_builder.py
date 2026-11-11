from app.models.schemas import ChatMessage
from app.rag.prompt_builder import (
    NO_CONTEXT_ANSWER,
    build_context,
    build_messages,
    trim_history,
)
from app.rag.retriever import RetrievedChunk


def make_chunk(index: int, text: str = "متن منبع", page: int | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"chunk-{index}",
        text=text,
        doc_id="doc-1",
        filename="آیین‌نامه.pdf",
        page=page,
        chunk_index=index,
        score=0.8,
    )


def test_context_has_numbered_headers_with_source():
    context, used = build_context([make_chunk(0, page=3)], 2000)

    assert context.startswith("[1] فایل: آیین‌نامه.pdf — صفحه: 3")
    assert len(used) == 1


def test_context_respects_char_budget():
    chunks = [make_chunk(index, text="ا" * 500) for index in range(6)]
    context, used = build_context(chunks, 1200)

    assert len(used) < len(chunks)
    assert len(context) <= 1200
    assert [int(line.split("]")[0].strip("[")) for line in context.split("\n") if line.startswith("[")] == list(
        range(1, len(used) + 1)
    )


def test_messages_layout_system_history_question():
    history = [
        ChatMessage(role="user", content="سؤال قبلی"),
        ChatMessage(role="assistant", content="پاسخ قبلی"),
    ]
    messages, used = build_messages(
        "سیاست مرخصی چیست؟",
        [make_chunk(0)],
        history,
        context_max_chars=2000,
        history_max_turns=6,
    )

    assert messages[0]["role"] == "system"
    assert "[1] فایل:" in messages[0]["content"]
    assert "پیدا نکردم" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "سؤال قبلی"},
        {"role": "assistant", "content": "پاسخ قبلی"},
        {"role": "user", "content": "سیاست مرخصی چیست؟"},
    ]
    assert len(used) == 1


def test_history_is_trimmed_to_last_turns():
    history = [ChatMessage(role="user", content=f"پیام {index}") for index in range(20)]
    trimmed = trim_history(history, 2)

    assert len(trimmed) == 4
    assert trimmed[-1]["content"] == "پیام 19"
    assert trim_history([], 6) == []
    assert trim_history(history, 0) == []


def test_no_context_answer_is_persian_refusal():
    assert "پیدا نکردم" in NO_CONTEXT_ANSWER
