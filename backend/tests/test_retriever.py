import asyncio

from app.rag.retriever import RetrievedChunk, retrieve, to_source


class FakeEmbedder:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FakeStore:
    def __init__(self, matches: list[dict]) -> None:
        self._matches = matches
        self.top_k: int | None = None

    def query(self, embedding: list[float], top_k: int) -> list[dict]:
        self.top_k = top_k
        return self._matches


def make_match(chunk_id: str, distance: float, page: int | None = None) -> dict:
    metadata = {"doc_id": "doc-1", "filename": "سیاست.pdf", "chunk_index": 2}
    if page is not None:
        metadata["page"] = page
    return {
        "chunk_id": chunk_id,
        "text": "متن قطعه",
        "metadata": metadata,
        "distance": distance,
    }


def test_threshold_filters_low_similarity():
    store = FakeStore([make_match("high", 0.1), make_match("low", 0.9)])
    embedder = FakeEmbedder()

    result = asyncio.run(
        retrieve("سؤال", embedder, store, top_k=5, threshold=0.5)
    )

    assert [chunk.chunk_id for chunk in result] == ["high"]
    assert result[0].score == 0.9
    assert embedder.queries == ["سؤال"]
    assert store.top_k == 5


def test_results_sorted_by_score_and_metadata_mapped():
    store = FakeStore([make_match("a", 0.4, page=7), make_match("b", 0.2, page=2)])

    result = asyncio.run(retrieve("سؤال", FakeEmbedder(), store, top_k=2, threshold=0.0))

    assert [chunk.chunk_id for chunk in result] == ["b", "a"]
    assert result[0].page == 2
    assert result[0].filename == "سیاست.pdf"
    assert result[0].chunk_index == 2


def test_blank_question_skips_embedding():
    embedder = FakeEmbedder()
    result = asyncio.run(retrieve("   ", embedder, FakeStore([]), top_k=3, threshold=0.2))

    assert result == []
    assert embedder.queries == []


def test_to_source_truncates_snippet():
    long_chunk = RetrievedChunk(
        chunk_id="a",
        text="ب" * 900,
        doc_id="doc-1",
        filename="سیاست.pdf",
        page=1,
        chunk_index=2,
        score=0.9,
    )

    source = to_source(long_chunk, snippet_chars=100)

    assert len(source.snippet) <= 101
    assert source.snippet.endswith("…")
    assert source.page == 1
    assert source.score == 0.9
