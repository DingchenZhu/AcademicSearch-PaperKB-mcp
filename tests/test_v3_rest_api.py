"""V3 tests: REST API endpoints (FastAPI TestClient, no real HTTP/DB/embedding)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.core.embedding.fake_embedder import FakeEmbedder
from src.core.kb_service import KBService, reset_kb_service
from src.core.kb_store.database import init_db
from src.core.kb_store.chunk_store import ChunkStore
from src.core.kb_store.paper_store import PaperStore
from src.core.models import IngestResult, Paper, PaperChunk, RetrievedChunk


# ---------------------------------------------------------------------------
# Fixtures: inject a real KBService backed by tmp SQLite + FakeEmbedder
# ---------------------------------------------------------------------------

@pytest.fixture
def kb_service(tmp_path):
    conn = init_db(tmp_path / "rest_test.sqlite")
    paper_store = PaperStore(conn)
    chunk_store = ChunkStore(conn)
    embedder = FakeEmbedder(dim=8)
    svc = KBService(paper_store, chunk_store, embedder)
    reset_kb_service(svc)
    yield svc
    reset_kb_service(None)


@pytest.fixture
def client(kb_service):
    from src.api.app import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/search_papers
# ---------------------------------------------------------------------------

ARXIV_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>The Transformer.</summary>
    <author><name>Vaswani</name></author>
    <published>2017-06-12T00:00:00Z</published>
  </entry>
</feed>
"""

class TestSearchPapersEndpoint:
    def test_returns_paper_list(self, client, httpx_mock):
        httpx_mock.add_response(text=ARXIV_ATOM)
        resp = client.post("/api/search_papers", json={"query": "transformer"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["title"] == "Attention Is All You Need"

    def test_empty_result(self, client, httpx_mock):
        httpx_mock.add_response(text='<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>')
        resp = client.post("/api/search_papers", json={"query": "zzz"})
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# /api/ingest_paper
# ---------------------------------------------------------------------------

class TestIngestEndpoint:
    def test_ingest_returns_result(self, client, kb_service, tmp_path):
        fake_text = "Deep learning attention mechanism. " * 50
        with (
            patch("src.core.kb_service.download_pdf", new=AsyncMock(return_value=tmp_path / "fake.pdf")),
            patch("src.core.kb_service.parse_pdf", return_value=fake_text),
        ):
            resp = client.post("/api/ingest_paper", json={
                "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                "title": "Attention Is All You Need",
                "source": "arxiv",
                "external_id": "1706.03762",
                "tags": ["transformer"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "paper_id" in data
        assert data["num_chunks"] > 0
        assert data["char_count"] > 0

    def test_ingest_stores_paper(self, client, kb_service, tmp_path):
        fake_text = "Convolutional network image classification. " * 30
        with (
            patch("src.core.kb_service.download_pdf", new=AsyncMock(return_value=tmp_path / "fake.pdf")),
            patch("src.core.kb_service.parse_pdf", return_value=fake_text),
        ):
            resp = client.post("/api/ingest_paper", json={
                "pdf_url": "https://example.com/cnn.pdf",
                "title": "CNN Paper",
                "source": "manual",
            })
        assert resp.status_code == 200
        paper_id = resp.json()["paper_id"]

        list_resp = client.post("/api/list_papers", json={})
        papers = list_resp.json()
        assert any(p["internal_id"] == paper_id for p in papers)


# ---------------------------------------------------------------------------
# /api/list_papers
# ---------------------------------------------------------------------------

class TestListPapersEndpoint:
    def _seed(self, kb_service: KBService):
        ps = kb_service._papers
        p1 = ps.upsert(Paper(source="arxiv", external_id="a1", title="Graph Neural Networks", year=2019))
        p2 = ps.upsert(Paper(source="arxiv", external_id="a2", title="BERT Pretraining", year=2018))
        ps.add_tags(p1, ["gnn"])
        return p1, p2

    def test_list_all(self, client, kb_service):
        self._seed(kb_service)
        resp = client.post("/api/list_papers", json={})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filter_by_tag(self, client, kb_service):
        self._seed(kb_service)
        resp = client.post("/api/list_papers", json={"tag": "gnn"})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Graph Neural Networks"

    def test_filter_by_keyword(self, client, kb_service):
        self._seed(kb_service)
        resp = client.post("/api/list_papers", json={"query": "BERT"})
        data = resp.json()
        assert len(data) == 1
        assert "BERT" in data[0]["title"]

    def test_empty_kb(self, client):
        resp = client.post("/api/list_papers", json={})
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# /api/search_kb  and  /api/qa_over_papers
# ---------------------------------------------------------------------------

class TestSearchKBEndpoint:
    def _seed_with_embeddings(self, kb_service: KBService):
        import asyncio
        ps = kb_service._papers
        cs = kb_service._chunks

        pid = ps.upsert(Paper(source="arxiv", external_id="emb.001", title="Emb Test"))
        texts = ["attention mechanism transformer", "random forest ensemble"]
        loop = asyncio.get_event_loop()
        embeddings = loop.run_until_complete(kb_service._embedder.embed(texts))
        chunks = [
            PaperChunk(paper_id=pid, chunk_index=i, text=t, embedding=emb)
            for i, (t, emb) in enumerate(zip(texts, embeddings))
        ]
        cs.insert_chunks(chunks)
        return pid

    def test_search_kb_returns_chunks(self, client, kb_service):
        self._seed_with_embeddings(kb_service)
        resp = client.post("/api/search_kb", json={"query": "transformer attention", "top_k": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) <= 2
        assert all("score" in item and "text" in item for item in data)

    def test_qa_over_papers_scoped(self, client, kb_service):
        pid = self._seed_with_embeddings(kb_service)
        resp = client.post("/api/qa_over_papers", json={
            "question": "attention mechanism",
            "paper_ids": [pid],
            "top_k": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert all(item["paper_id"] == pid for item in data)


# ---------------------------------------------------------------------------
# /api/tag_paper
# ---------------------------------------------------------------------------

class TestTagPaperEndpoint:
    def test_tag_paper(self, client, kb_service):
        pid = kb_service._papers.upsert(
            Paper(source="arxiv", external_id="tag.001", title="Tag Me")
        )
        resp = client.post("/api/tag_paper", json={"paper_id": pid, "tags": ["ml", "survey"]})
        assert resp.status_code == 200
        assert resp.json()["tags_added"] == ["ml", "survey"]

        papers = client.post("/api/list_papers", json={"tag": "survey"}).json()
        assert any(p["internal_id"] == pid for p in papers)
