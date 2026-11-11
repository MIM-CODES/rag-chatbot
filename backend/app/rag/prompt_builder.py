"""ساخت prompt نهایی با رشته‌سازی ساده‌ی پایتون (بدون PromptTemplate فریمورک)."""

from __future__ import annotations

from app.models.schemas import ChatMessage
from app.rag.retriever import RetrievedChunk

SYSTEM_PROMPT_TEMPLATE = """تو دستیار دانش سازمانی هستی و فقط بر اساس «منابع» زیر پاسخ می‌دهی.

قواعد پاسخ‌دهی:
1. تنها از اطلاعات موجود در منابع استفاده کن؛ هیچ دانش بیرونی، حدس یا تکمیل از خودت اضافه نکن.
2. اگر پاسخ در منابع نیست، دقیقاً این جمله را بنویس: «در اسناد موجود پاسخی برای این سؤال پیدا نکردم.»
3. در پایان هر جمله یا بندی که از یک منبع آمده، شماره‌ی آن منبع را به شکل [1] ذکر کن.
4. پاسخ را فارسی، روشن و کوتاه بنویس. اگر منابع با هم تناقض دارند، هر دو را با ذکر منبع بیان کن.

منابع:
{context}
"""

NO_CONTEXT_ANSWER = "در اسناد موجود پاسخی برای این سؤال پیدا نکردم."

MAX_HISTORY_MESSAGE_CHARS = 1200


def build_context(
    chunks: list[RetrievedChunk],
    context_max_chars: int,
) -> tuple[str, list[RetrievedChunk]]:
    """ساخت بلوک‌های شماره‌دار منابع با رعایت بودجه‌ی کاراکتر."""
    blocks: list[str] = []
    used: list[RetrievedChunk] = []
    total = 0

    for position, chunk in enumerate(chunks, start=1):
        header = f"[{position}] فایل: {chunk.filename}"
        if chunk.page is not None:
            header += f" — صفحه: {chunk.page}"
        body = chunk.text.strip()

        remaining = context_max_chars - total
        if remaining <= len(header) + 40:
            break
        allowed = remaining - len(header) - 2
        if len(body) > allowed:
            body = body[:allowed].rstrip() + "…"

        block = f"{header}\n{body}"
        blocks.append(block)
        used.append(chunk)
        total += len(block) + 2

    return "\n\n".join(blocks), used


def trim_history(history: list[ChatMessage], max_turns: int) -> list[dict[str, str]]:
    """نگه‌داشتن آخرین n نوبت گفتگو (هر نوبت = پیام کاربر + پاسخ)."""
    if max_turns <= 0 or not history:
        return []
    trimmed = history[-max_turns * 2 :]
    messages: list[dict[str, str]] = []
    for message in trimmed:
        content = message.content.strip()
        if not content:
            continue
        if len(content) > MAX_HISTORY_MESSAGE_CHARS:
            content = content[:MAX_HISTORY_MESSAGE_CHARS] + "…"
        messages.append({"role": message.role, "content": content})
    return messages


def build_messages(
    question: str,
    chunks: list[RetrievedChunk],
    history: list[ChatMessage],
    *,
    context_max_chars: int,
    history_max_turns: int,
) -> tuple[list[dict[str, str]], list[RetrievedChunk]]:
    """پیام‌های آماده برای API چت + منابعی که واقعاً داخل context رفتند."""
    context, used = build_context(chunks, context_max_chars)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context or "(منبعی یافت نشد)")
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(trim_history(history, history_max_turns))
    messages.append({"role": "user", "content": question.strip()})
    return messages, used
