from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.rag.vector_store import VectorStore
from app.runtime import Components
from app.services.registry import DocumentRegistry

SAMPLE_TEXT = (
    "سیاست مرخصی استعلاجی: کارمند باید گواهی پزشک معتمد را تحویل دهد. "
    "مرخصی استعلاجی تا ۳۰ روز در سال با پرداخت کامل حقوق همراه است. "
) * 6


class FakeEmbedder:
    dimension = 16

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for index, char in enumerate(text[:200]):
            vector[index % self.dimension] += (ord(char) % 97 + 1) / 97.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeLLM:
    async def complete(self, messages: list[dict]) -> str:
        return "پاسخ آزمایشی بر اساس منبع [1]."

    async def stream(self, messages: list[dict]):
        for token in ["پاسخ ", "آزمایشی ", "[1]."]:
            yield token

    async def check(self) -> bool:
        return True


def build_client(tmp_path, **overrides):
    settings = Settings(
        _env_file=None,
        llm_model="fake-chat",
        embedding_model="fake-embed",
        chroma_persist_dir=tmp_path / "chroma",
        raw_documents_dir=tmp_path / "raw",
        chunk_size=150,
        chunk_overlap=30,
        retrieval_top_k=3,
        similarity_threshold=-1.0,
        context_max_chars=1000,
        max_upload_mb=1,
        **overrides,
    )
    settings.ensure_directories()
    components = Components(
        settings=settings,
        embedder=FakeEmbedder(),
        store=VectorStore(
            persist_dir=settings.chroma_persist_dir,
            collection_name="test_collection",
            embedding_model=settings.embedding_model,
        ),
        llm=FakeLLM(),
        registry=DocumentRegistry(settings.raw_documents_dir.parent / "registry.json"),
    )
    return TestClient(create_app(settings=settings, components=components)), components


def test_health_reports_ready_service(tmp_path):
    client, _ = build_client(tmp_path)

    with client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chunk_count"] == 0
    assert body["llm_model"] == "fake-chat"
    assert body["diagnostics"] == []


def test_ingest_chat_stream_and_delete(tmp_path):
    client, components = build_client(tmp_path)

    with client:
        ingest = client.post(
            "/api/ingest",
            files={"files": ("leave.txt", SAMPLE_TEXT.encode("utf-8"), "text/plain")},
        )
        assert ingest.status_code == 200
        result = ingest.json()["results"][0]
        assert result["status"] == "indexed", result
        assert result["chunks"] > 1

        documents = client.get("/api/documents").json()
        assert len(documents) == 1
        assert documents[0]["filename"] == "leave.txt"
        assert documents[0]["embedding_model"] == "fake-embed"

        chat = client.post("/api/chat", json={"message": "مرخصی استعلاجی چند روز است؟"})
        assert chat.status_code == 200
        body = chat.json()
        assert body["sources"], body
        assert body["answer"] == "پاسخ آزمایشی بر اساس منبع [1]."
        assert body["conversation_id"]

        stream = client.post(
            "/api/chat/stream", json={"message": "مرخصی استعلاجی چند روز است؟"}
        )
        assert stream.status_code == 200
        assert "event: sources" in stream.text
        assert "event: token" in stream.text
        assert "event: done" in stream.text

        deleted = client.delete(f"/api/documents/{documents[0]['doc_id']}")
        assert deleted.status_code == 200
        assert client.get("/api/documents").json() == []
        assert components.store.count() == 0
        assert client.delete(f"/api/documents/{documents[0]['doc_id']}").status_code == 404


def test_ingest_rejects_unsupported_extension(tmp_path):
    client, _ = build_client(tmp_path)

    with client:
        response = client.post(
            "/api/ingest",
            files={"files": ("notes.exe", b"binary", "application/octet-stream")},
        )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "failed"
    assert "پسوند" in result["error"]


def test_ingest_rejects_too_large_file(tmp_path):
    client, _ = build_client(tmp_path)
    too_large = ("متن " * 400_000).encode("utf-8")  # > 1MB

    with client:
        response = client.post(
            "/api/ingest", files={"files": ("big.txt", too_large, "text/plain")}
        )

    result = response.json()["results"][0]
    assert result["status"] == "failed"
    assert "حجم" in result["error"]


def test_chat_without_documents_returns_refusal(tmp_path):
    client, _ = build_client(tmp_path)

    with client:
        response = client.post("/api/chat", json={"message": "هرچیزی"})

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == []
    assert "پیدا نکردم" in body["answer"]
