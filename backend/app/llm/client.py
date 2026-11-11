"""کلاینت مدل زبانی روی API سازگار با OpenAI (پیش‌فرض: Ollama) با streaming."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    NotFoundError,
)

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """خطای مدل زبانی با پیام فارسی و کد وضعیت مناسب."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "ollama",
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    # ---------- کمکی ----------

    def _translate(self, exc: Exception) -> LLMError:
        model = self._settings.llm_model or "؟"
        base_url = self._settings.llm_base_url

        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return LLMError(
                f"اتصال به سرویس مدل زبانی ({base_url}) برقرار نشد. "
                "مطمئن شوید Ollama در حال اجراست (ollama serve) و LLM_BASE_URL درست است.",
                status_code=503,
            )
        if isinstance(exc, NotFoundError):
            return LLMError(
                f"مدل «{model}» در سرویس پیدا نشد. با دستور `ollama pull {model}` دانلودش کنید.",
                status_code=400,
            )
        if isinstance(exc, APIStatusError):
            if exc.status_code == 404:
                return LLMError(
                    f"مدل «{model}» در سرویس پیدا نشد. با دستور `ollama pull {model}` دانلودش کنید.",
                    status_code=400,
                )
            if exc.status_code in (401, 403):
                return LLMError(
                    "دسترسی سرویس مدل رد شد؛ LLM_API_KEY را بررسی کنید.", status_code=502
                )
            detail = str(getattr(exc, "message", "") or exc)[:300]
            return LLMError(
                f"سرویس مدل زبانی خطا برگرداند (HTTP {exc.status_code}): {detail}",
                status_code=502,
            )
        return LLMError(f"خطای غیرمنتظره در فراخوانی مدل: {exc}", status_code=500)

    def _ensure_model(self) -> str:
        if not self._settings.llm_model:
            raise LLMError(
                "LLM_MODEL در backend/.env تنظیم نشده است. نام مدل چت موجود در Ollama را وارد کنید.",
                status_code=409,
            )
        return self._settings.llm_model

    def _payload(self, messages: list[dict[str, str]], stream: bool) -> dict:
        return {
            "model": self._ensure_model(),
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.llm_max_tokens,
            "stream": stream,
        }

    # ---------- عمومی ----------

    async def complete(self, messages: list[dict[str, str]]) -> str:
        try:
            response = await self._client.chat.completions.create(**self._payload(messages, False))
        except LLMError:
            raise
        except Exception as exc:
            raise self._translate(exc) from exc

        if not response.choices:
            raise LLMError("مدل پاسخی برنگرداند.")
        return (response.choices[0].message.content or "").strip()

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        try:
            response = await self._client.chat.completions.create(**self._payload(messages, True))
        except LLMError:
            raise
        except Exception as exc:
            raise self._translate(exc) from exc

        try:
            async for event in response:
                if not event.choices:
                    continue
                delta = event.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except Exception as exc:
            raise self._translate(exc) from exc

    async def check(self) -> bool:
        """بررسی سریع دسترسی به سرویس مدل (برای /api/health)."""
        try:
            await asyncio.wait_for(self._client.models.list(), timeout=3.0)
            return True
        except Exception:
            return False
