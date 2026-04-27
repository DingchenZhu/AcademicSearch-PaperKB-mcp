"""V2 tests: FaissRetriever + factory, parity with linear cosine retriever.

Tests verify:
  - FaissRetriever finds the same top-1 as KBRetriever on identical data
  - Scores are in [−1, 1] (inner-product of L2-normalised vectors = cosine)
  - paper_ids filter works
  - Index auto-rebuilds when new chunks are added
  - factory() returns the right class based on KB_RETRIEVER_BACKEND env var
  - Empty KB returns empty results
"""

from __future__ import annotations

import os

import pytest

from src.core.embedding.fake_embedder import FakeEmbedder
from src.core.kb_query.faiss_retriever import FaissRetriever
from src.core.kb_query.retriever import KBRetriever
from src.core.kb_query.factory import make_retriever
from src.core.kb_store.chunk_store import ChunkStore
from src.core.kb_store.database import init_db
from src.core.kb_store.paper_store import PaperStore
from src.core.models import Paper, PaperChunk

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return init_db(tmp_path / "test_v2.sqlite")

@pytest.fixture
def stores(db):
    return PaperStore(db), ChunkStore(db)

@pytest.fixture
def embedder():
    return FakeEmbedder(dim=16)   # larger dim → more distinct vectors

@pytest.fixture
def faiss_ret(stores, embedder):
    _, chunk_store = stores
    return FaissRetriever(chunk_store, embedder)

@pytest.fixture
def linear_ret(stores, embedder):
    _, chunk_store = stores
    return KBRetriever(chunk_store, embedder)


# Helper: ingest a list of (paper_id, text) pairs into chunk_store
async def _ingest(chunk_store: ChunkStore, embedder: FakeEmbedder, pairs: list[tuple[str, str]]) -> None:
    chunks = []
    texts = [text for _, text in pairs]
    embeddings = await embedder.embed(texts)
    for (pid, text), emb in zip(pairs, embeddings):
        chunks.append(PaperChunk(paper_id=pid, chunk_index=0, text=text, embedding=emb))
    chunk_store.insert_chunks(chunks)


# ---------------------------------------------------------------------------
# Parity with linear retriever
# ---------------------------------------------------------------------------

class TestFaissRetrieverParity:
    @pytest.mark.asyncio
    async def test_top1_matches_linear(self, stores, embedder, faiss_ret, linear_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="par.001", title="P"))
        await _ingest(chunk_store, embedder, [
            (p, "deep learning attention transformer"),
            (p, "random forest decision tree"),
            (p, "ocean waves tides"),
        ])

        query = "transformer attention mechanism"
        f_res = await faiss_ret.search(query, top_k=1)
        l_res = await linear_ret.search(query, top_k=1)
        assert f_res[0].text == l_res[0].text, "Top-1 differs between FAISS and linear"

    @pytest.mark.asyncio
    async def test_all_scores_in_valid_range(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="range.001", title="R"))
        await _ingest(chunk_store, embedder, [(p, f"text sample {i}") for i in range(5)])
        results = await faiss_ret.search("sample text", top_k=5)
        for r in results:
            assert -1.0 <= r.score <= 1.01, f"score {r.score} out of cosine range"

    @pytest.mark.asyncio
    async def test_scores_descending(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="order.001", title="O"))
        texts = [
            "attention is all you need transformer",
            "classification tree boosting",
            "ocean marine biology",
        ]
        await _ingest(chunk_store, embedder, [(p, t) for t in texts])
        results = await faiss_ret.search("attention transformer model", top_k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# paper_ids filter
# ---------------------------------------------------------------------------

class TestFaissRetrieverFilter:
    @pytest.mark.asyncio
    async def test_paper_ids_filter(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p1 = paper_store.upsert(Paper(source="arxiv", external_id="fa.001", title="P1"))
        p2 = paper_store.upsert(Paper(source="arxiv", external_id="fa.002", title="P2"))
        await _ingest(chunk_store, embedder, [
            (p1, "neural network deep learning"),
            (p2, "support vector machine kernel"),
        ])
        results = await faiss_ret.search("neural network", top_k=5, paper_ids=[p1])
        assert all(r.paper_id == p1 for r in results)

    @pytest.mark.asyncio
    async def test_empty_paper_ids_searches_all(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p1 = paper_store.upsert(Paper(source="arxiv", external_id="all.001", title="A1"))
        p2 = paper_store.upsert(Paper(source="arxiv", external_id="all.002", title="A2"))
        await _ingest(chunk_store, embedder, [(p1, "text A"), (p2, "text B")])
        results = await faiss_ret.search("text", top_k=5)
        pids = {r.paper_id for r in results}
        assert p1 in pids and p2 in pids


# ---------------------------------------------------------------------------
# Index auto-rebuild
# ---------------------------------------------------------------------------

class TestFaissIndexRebuild:
    @pytest.mark.asyncio
    async def test_index_rebuilds_after_ingest(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="rebuild.001", title="R"))

        # First search on empty KB
        assert await faiss_ret.search("anything", top_k=3) == []

        # Ingest then search again — should auto-rebuild
        await _ingest(chunk_store, embedder, [(p, "graph neural network node classification")])
        results = await faiss_ret.search("graph neural", top_k=1)
        assert len(results) == 1
        assert results[0].paper_id == p

    @pytest.mark.asyncio
    async def test_new_chunk_appears_in_results(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="new.001", title="N"))

        await _ingest(chunk_store, embedder, [(p, "convolutional neural network image classification")])
        _ = await faiss_ret.search("image", top_k=1)   # build index

        # Add a second, more relevant chunk
        new_text = "image segmentation semantic pixel labeling"
        new_emb = await embedder.embed_one(new_text)
        chunk_store.insert_chunks([PaperChunk(paper_id=p, chunk_index=1, text=new_text, embedding=new_emb)])

        results = await faiss_ret.search("semantic image segmentation", top_k=2)
        texts = [r.text for r in results]
        assert new_text in texts, "Newly ingested chunk not found after auto-rebuild"

    @pytest.mark.asyncio
    async def test_explicit_rebuild(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="expl.001", title="E"))
        await _ingest(chunk_store, embedder, [(p, "language model pretraining fine-tuning")])

        faiss_ret.rebuild_index()
        assert faiss_ret._index is not None
        assert faiss_ret._index.ntotal == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestFaissRetrieverEdge:
    @pytest.mark.asyncio
    async def test_empty_kb(self, faiss_ret):
        results = await faiss_ret.search("anything", top_k=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_top_k_larger_than_index(self, stores, embedder, faiss_ret):
        paper_store, chunk_store = stores
        p = paper_store.upsert(Paper(source="arxiv", external_id="small.001", title="S"))
        await _ingest(chunk_store, embedder, [(p, "only one chunk here")])
        results = await faiss_ret.search("chunk", top_k=100)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestRetrieverFactory:
    def test_linear_by_default(self, stores, embedder, monkeypatch):
        monkeypatch.delenv("KB_RETRIEVER_BACKEND", raising=False)
        _, chunk_store = stores
        r = make_retriever(chunk_store, embedder)
        assert isinstance(r, KBRetriever)

    def test_linear_explicit(self, stores, embedder, monkeypatch):
        monkeypatch.setenv("KB_RETRIEVER_BACKEND", "linear")
        _, chunk_store = stores
        r = make_retriever(chunk_store, embedder)
        assert isinstance(r, KBRetriever)

    def test_faiss_backend(self, stores, embedder, monkeypatch):
        monkeypatch.setenv("KB_RETRIEVER_BACKEND", "faiss")
        _, chunk_store = stores
        r = make_retriever(chunk_store, embedder)
        assert isinstance(r, FaissRetriever)
