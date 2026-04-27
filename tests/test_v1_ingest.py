"""V1 tests: PDF ingest pipeline + KB retrieval with FakeEmbedder.

Tests cover:
  - chunker edge cases
  - FakeEmbedder determinism and unit-normalization
  - full ingest round-trip (download mock → parse → chunk → embed → store)
  - linear cosine retriever (KBRetriever) ranking
  - ingest idempotency and multi-paper search scope
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.core.embedding.fake_embedder import FakeEmbedder
from src.core.kb_query.retriever import KBRetriever
from src.core.kb_store.chunk_store import ChunkStore
from src.core.kb_store.database import init_db
from src.core.kb_store.paper_store import PaperStore
from src.core.models import Paper, PaperChunk
from src.core.pdf_ingest.chunker import chunk_text

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return init_db(tmp_path / "test.sqlite")

@pytest.fixture
def stores(db):
    return PaperStore(db), ChunkStore(db)

@pytest.fixture
def embedder():
    return FakeEmbedder(dim=8)

@pytest.fixture
def retriever(stores, embedder):
    _, chunk_store = stores
    return KBRetriever(chunk_store, embedder)


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

class TestChunker:
    def test_overlap_preserved(self):
        text = "a" * 2500
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        assert chunks[0][-200:] == chunks[1][:200]

    def test_empty_string(self):
        assert chunk_text("") == []

    def test_whitespace_only(self):
        assert chunk_text("   \n\t ") == []

    def test_single_chunk_when_text_fits(self):
        assert chunk_text("hello world", chunk_size=1000) == ["hello world"]

    def test_no_duplicate_content_at_non_overlap(self):
        text = "x" * 3000
        chunks = chunk_text(text, chunk_size=1000, overlap=0)
        reconstructed = "".join(chunks)
        assert reconstructed == text

    def test_chunk_count(self):
        # step = 1000 - 100 = 900; starts: 0, 900, 1800, 2700 → 4 chunks (last is partial)
        chunks = chunk_text("a" * 3000, chunk_size=1000, overlap=100)
        assert len(chunks) == 4


# ---------------------------------------------------------------------------
# FakeEmbedder
# ---------------------------------------------------------------------------

class TestFakeEmbedder:
    @pytest.mark.asyncio
    async def test_deterministic(self, embedder):
        v1 = await embedder.embed_one("hello world")
        v2 = await embedder.embed_one("hello world")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_different_texts_different_vectors(self, embedder):
        v1 = await embedder.embed_one("attention is all you need")
        v2 = await embedder.embed_one("graph neural networks for drug discovery")
        assert v1 != v2

    @pytest.mark.asyncio
    async def test_unit_norm(self, embedder):
        v = await embedder.embed_one("test text")
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_batch_equals_individual(self, embedder):
        texts = ["foo", "bar", "baz"]
        batch = await embedder.embed(texts)
        singles = [await embedder.embed_one(t) for t in texts]
        assert batch == singles

    @pytest.mark.asyncio
    async def test_empty_batch(self, embedder):
        assert await embedder.embed([]) == []


# ---------------------------------------------------------------------------
# Full ingest round-trip
# ---------------------------------------------------------------------------

class TestIngestPipeline:
    @pytest.mark.asyncio
    async def test_ingest_stores_chunks_with_embeddings(self, stores, embedder, tmp_path):
        paper_store, chunk_store = stores
        paper = Paper(source="arxiv", external_id="1234.5678", title="Test", url_pdf="http://x/1.pdf")
        pid = paper_store.upsert(paper)

        raw_text = "Deep learning has transformed many fields. " * 60
        chunks_text = chunk_text(raw_text, chunk_size=200, overlap=20)
        chunks = [PaperChunk(paper_id=pid, chunk_index=i, text=t) for i, t in enumerate(chunks_text)]
        embeddings = await embedder.embed([c.text for c in chunks])
        for c, emb in zip(chunks, embeddings):
            c.embedding = emb
        chunk_store.insert_chunks(chunks)

        stored = chunk_store.get_chunks_by_paper(pid)
        assert len(stored) == len(chunks)
        assert all(c.embedding is not None for c in stored)
        assert chunk_store.count_by_paper(pid) == len(chunks)

    @pytest.mark.asyncio
    async def test_ingest_idempotent(self, stores, embedder):
        paper_store, chunk_store = stores
        paper = Paper(source="arxiv", external_id="idem.001", title="Idem")
        pid1 = paper_store.upsert(paper)
        pid2 = paper_store.upsert(paper)
        assert pid1 == pid2

    @pytest.mark.asyncio
    async def test_ingest_with_tags(self, stores):
        paper_store, _ = stores
        paper = Paper(source="arxiv", external_id="tag.001", title="Tagged")
        pid = paper_store.upsert(paper)
        paper_store.add_tags(pid, ["nlp", "transformer"])
        results = paper_store.list(tag="transformer")
        assert any(p.internal_id == pid for p in results)
        assert not paper_store.list(tag="physics")

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocked_pdf(self, stores, embedder, tmp_path):
        """Simulate the server-side ingest flow without real HTTP/PDF."""
        from src.core.pdf_ingest.chunker import chunk_text

        paper_store, chunk_store = stores
        fake_text = "Transformers use multi-head attention. " * 80
        pdf_url = "https://arxiv.org/pdf/1706.03762.pdf"

        paper = Paper(source="arxiv", external_id="1706.03762",
                      title="Attention Is All You Need", url_pdf=pdf_url)
        pid = paper_store.upsert(paper)

        # Mock download+parse so we don't need real network/PDF
        with patch("src.core.pdf_ingest.downloader.download_pdf",
                   new=AsyncMock(return_value=tmp_path / "fake.pdf")):
            with patch("src.core.pdf_ingest.parser.parse_pdf", return_value=fake_text):
                from src.core.pdf_ingest import download_pdf, parse_pdf
                pdf_path = await download_pdf(pdf_url)
                text = parse_pdf(pdf_path)

        raw_chunks = chunk_text(text, chunk_size=300, overlap=50)
        chunks = [PaperChunk(paper_id=pid, chunk_index=i, text=c) for i, c in enumerate(raw_chunks)]
        embeddings = await embedder.embed([c.text for c in chunks])
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb
        chunk_store.insert_chunks(chunks)

        assert chunk_store.count_by_paper(pid) == len(raw_chunks)


# ---------------------------------------------------------------------------
# KBRetriever (linear cosine)
# ---------------------------------------------------------------------------

class TestKBRetriever:
    @pytest.mark.asyncio
    async def test_top_k_respected(self, stores, embedder, retriever):
        paper_store, chunk_store = stores
        paper = Paper(source="arxiv", external_id="ret.001", title="Ret")
        pid = paper_store.upsert(paper)
        chunks = [
            PaperChunk(paper_id=pid, chunk_index=i, text=f"sentence about topic {i}")
            for i in range(10)
        ]
        embeddings = await embedder.embed([c.text for c in chunks])
        for c, emb in zip(chunks, embeddings):
            c.embedding = emb
        chunk_store.insert_chunks(chunks)

        results = await retriever.search("topic sentence", top_k=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_scores_descending(self, stores, embedder, retriever):
        paper_store, chunk_store = stores
        paper = Paper(source="arxiv", external_id="ret.002", title="Score order")
        pid = paper_store.upsert(paper)

        query = "neural network training"
        # One chunk semantically close to query, others noise
        texts = [
            "neural network training gradient descent",
            "banana apple fruit salad",
            "ocean waves beach sunset",
        ]
        chunks = [PaperChunk(paper_id=pid, chunk_index=i, text=t) for i, t in enumerate(texts)]
        embeddings = await embedder.embed([c.text for c in chunks])
        for c, emb in zip(chunks, embeddings):
            c.embedding = emb
        chunk_store.insert_chunks(chunks)

        results = await retriever.search(query, top_k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "scores not descending"

    @pytest.mark.asyncio
    async def test_paper_id_filter(self, stores, embedder, retriever):
        paper_store, chunk_store = stores

        p1 = paper_store.upsert(Paper(source="arxiv", external_id="filt.001", title="P1"))
        p2 = paper_store.upsert(Paper(source="arxiv", external_id="filt.002", title="P2"))

        for pid, text in [(p1, "attention mechanism neural"), (p2, "random forest decision tree")]:
            emb = await embedder.embed_one(text)
            chunk_store.insert_chunks([PaperChunk(paper_id=pid, chunk_index=0, text=text, embedding=emb)])

        results = await retriever.search("attention neural", top_k=5, paper_ids=[p1])
        assert all(r.paper_id == p1 for r in results)

    @pytest.mark.asyncio
    async def test_empty_kb_returns_empty(self, retriever):
        results = await retriever.search("anything", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_chunks_without_embeddings_excluded(self, stores, embedder, retriever):
        paper_store, chunk_store = stores
        paper = Paper(source="arxiv", external_id="noEmb.001", title="NoEmb")
        pid = paper_store.upsert(paper)
        # Insert chunk without embedding
        chunk_store.insert_chunks([PaperChunk(paper_id=pid, chunk_index=0, text="text without emb")])
        results = await retriever.search("text", top_k=5)
        assert results == []
