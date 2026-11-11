"""تنظیمات برنامه؛ همه‌ی مقادیر از فایل .env خوانده و اعتبارسنجی می‌شوند."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """پیکربندی مرکزی؛ نام متغیرها در .env با حروف بزرگ نوشته می‌شود."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- مدل زبانی (سازگار با OpenAI؛ پیش‌فرض: Ollama) ---
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    llm_timeout_seconds: float = 180.0

    # --- Embedding ---
    embedding_base_url: str = "http://localhost:11434/v1"
    embedding_api_key: str = "ollama"
    embedding_model: str = ""
    embedding_batch_size: int = 32
    embedding_timeout_seconds: float = 180.0

    # --- ChromaDB ---
    chroma_persist_dir: Path = Path("./data/chroma_db")
    chroma_collection_name: str = "company_knowledge_base"

    # --- Chunking ---
    chunk_size: int = 800
    chunk_overlap: int = 120

    # --- Retrieval ---
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.25
    context_max_chars: int = 6000

    # --- اپلیکیشن ---
    history_max_turns: int = 6
    max_upload_mb: int = 25
    cors_allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    raw_documents_dir: Path = Path("./data/raw_documents")
    log_level: str = "INFO"

    # ---------- اعتبارسنجی ----------

    @field_validator("chroma_persist_dir", "raw_documents_dir", mode="after")
    @classmethod
    def _resolve_path(cls, value: Path) -> Path:
        """مسیرهای نسبی همیشه نسبت به پوشه‌ی backend حل می‌شوند، نه cwd."""
        value = Path(value).expanduser()
        return value if value.is_absolute() else (BACKEND_DIR / value).resolve()

    @field_validator("llm_base_url", "embedding_base_url", mode="after")
    @classmethod
    def _clean_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("llm_model", "embedding_model", mode="after")
    @classmethod
    def _clean_model_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _validate_ranges(self) -> "Settings":
        problems: list[str] = []
        if self.chunk_size < 100:
            problems.append("CHUNK_SIZE باید حداقل ۱۰۰ باشد.")
        if self.chunk_overlap < 0:
            problems.append("CHUNK_OVERLAP نمی‌تواند منفی باشد.")
        if self.chunk_overlap >= self.chunk_size:
            problems.append("CHUNK_OVERLAP باید کوچک‌تر از CHUNK_SIZE باشد.")
        if self.embedding_batch_size < 1:
            problems.append("EMBEDDING_BATCH_SIZE باید حداقل ۱ باشد.")
        if self.retrieval_top_k < 1:
            problems.append("RETRIEVAL_TOP_K باید حداقل ۱ باشد.")
        if not -1.0 <= self.similarity_threshold <= 1.0:
            problems.append("SIMILARITY_THRESHOLD باید بین -۱ و ۱ باشد.")
        if self.context_max_chars < self.chunk_size:
            problems.append("CONTEXT_MAX_CHARS باید بزرگ‌تر یا مساوی CHUNK_SIZE باشد.")
        if self.max_upload_mb < 1:
            problems.append("MAX_UPLOAD_MB باید حداقل ۱ باشد.")
        if not 1 <= self.app_port <= 65535:
            problems.append("APP_PORT معتبر نیست.")
        if problems:
            raise ValueError(" | ".join(problems))
        return self

    # ---------- کمکی ----------

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def missing_settings(self) -> list[str]:
        """متغیرهای لازم که هنوز در .env مقدار نگرفته‌اند."""
        missing: list[str] = []
        if not self.llm_model:
            missing.append("LLM_MODEL")
        if not self.embedding_model:
            missing.append("EMBEDDING_MODEL")
        return missing

    def ensure_directories(self) -> None:
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        self.raw_documents_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
