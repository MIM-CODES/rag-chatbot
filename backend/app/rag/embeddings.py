"""تولید embedding از طریق API سازگار با OpenAI (پیش‌فرض: Ollama)."""

from __future__ import annotations

import asyncio
import logging

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    NotFoundError,
)

from app.config import Settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class EmbeddingError(Exception):
    """خطای embedding با پیام فارسی قابل نمایش در UI."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class Embedder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key or "ollama",
            timeout=settings.embedding_timeout_seconds,
            max_retries=0,
        )
        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def _model_hint(self) -> str:
        model = self._settings.embedding_model
        return (
            f"مدل embedding «{model}» در سرویس پیدا نشد. "
            f"آن را دانلود کنید: ollama pull {model}"
        )

    def _check_dimension(self, vector: list[float]) -> list[float]:
        if not vector:
            raise EmbeddingError("سرویس embedding بردار خالی برگرداند.")
        if self._dimension is None:
            self._dimension = len(vector)
        elif len(vector) != self._dimension:
            raise EmbeddingError(
                "ابعاد بردار embedding در میانه‌ی پردازش تغییر کرد؛ "
                "مدل embedding را ثابت نگه دارید و دوباره ایندکس کنید.",
                status_code=409,
            )
        return vector

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._settings.embedding_model:
            raise EmbeddingError(
                "EMBEDDING_MODEL در backend/.env تنظیم نشده است. "
                "نام مدل embedding موجود در Ollama را وارد کنید.",
                status_code=409,
            )

        vectors: list[list[float]] = []
        batch_size = self._settings.embedding_batch_size
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        model = self._settings.embedding_model
        last_error: Exception | None = None

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await self._client.embeddings.create(model=model, input=batch)
                ordered = sorted(response.data, key=lambda item: item.index)
                vectors = [self._check_dimension(list(item.embedding)) for item in ordered]
                if len(vectors) != len(batch):
                    raise EmbeddingError(
                        "تعداد بردارهای برگشتی با تعداد قطعات ارسالی برابر نیست."
                    )
                return vectors
            except EmbeddingError:
                raise
            except NotFoundError as exc:
                raise EmbeddingError(self._model_hint(), status_code=400) from exc
            except (APIConnectionError, APITimeoutError) as exc:
                last_error = exc
                logger.warning("اتصال به سرویس embedding ناموفق (تلاش %s): %s", attempt + 1, exc)
                await asyncio.sleep(0.5 * (2**attempt))
            except APIStatusError as exc:
                if exc.status_code == 404:
                    raise EmbeddingError(self._model_hint(), status_code=400) from exc
                if exc.status_code in (401, 403):
                    raise EmbeddingError(
                        "دسترسی سرویس embedding رد شد؛ EMBEDDING_API_KEY را بررسی کنید.",
                        status_code=502,
                    ) from exc
                last_error = exc
                logger.warning("سرویس embedding خطا داد (HTTP %s)", exc.status_code)
                await asyncio.sleep(0.5 * (2**attempt))

        raise EmbeddingError(
            "سرویس embedding پاسخ نداد. مطمئن شوید Ollama در حال اجراست "
            f"({self._settings.embedding_base_url}) و شبکه در دسترس است."
            + (f" آخرین خطا: {last_error}" if last_error else "")
        )

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]
