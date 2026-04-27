"""V3 tests: MCP server tool handlers via FastMCP.call_tool().

Tests exercise the actual tool handler code paths without starting an HTTP
server, using KBService backed by in-memory SQLite and FakeEmbedder.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.embedding.fake_embedder import FakeEmbedder
from src.core.kb_service import KBService, reset_kb_service
from src.core.kb_store.chunk_store import ChunkStore
from src.core.kb_store.database import init_db
from src.core.kb_store.paper_store import PaperStore
from src.core.models import Paper, PaperChunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unwrap(result):
    """Extract the actual return value from FastMCP.call_tool() in mcp 1.27+.

    FastMCP uses two different wire formats depending on tool return type:
      - list[dict] tools  → (content_blocks, {'result': actual_list})
      - dict tools        → [TextContent(type='text', text=<json_str>)]
    """
    import json as _json

    if isinstance(result, tuple) and len(result) == 2:
        structured = result[1]
        if isinstance(structured, dict):
            return structured.get("result", structured)
        return structured

    # TextContent list (single dict return or error dict)
    if isinstance(result, list) and result and hasattr(result[0], "text"):
        try:
            return _json.loads(result[0].text)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def kb_service(tmp_path):
    conn = init_db(tmp_path / "mcp_test.sqlite")
    paper_store = PaperStore(conn)
    chunk_store = ChunkStore(conn)
    embedder = FakeEmbedder(dim=8)
    svc = KBService(paper_store, chunk_store, embedder)
    reset_kb_service(svc)
    yield svc
    reset_kb_service(None)


@pytest.fixture
def mcp_server(kb_service):
    from src.servers.paper_kb_server import mcp
    return mcp


@pytest.fixture
def search_server():
    from src.servers.academic_search_server import mcp
    return mcp


# ---------------------------------------------------------------------------
# AcademicSearch MCP tools
# ---------------------------------------------------------------------------

ARXIV_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>The Transformer architecture.</summary>
    <author><name>Ashish Vaswani</name></author>
    <published>2017-06-12T00:00:00Z</published>
  </entry>
</feed>
"""

@pytest.mark.asyncio
class TestAcademicSearchMCPTools:
    async def test_search_papers_tool(self, search_server, httpx_mock):
        httpx_mock.add_response(text=ARXIV_ATOM)
        result = _unwrap(await search_server.call_tool(
            "search_papers_tool",
            {"query": "transformer", "max_results": 5},
        ))
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["title"] == "Attention Is All You Need"

    async def test_get_paper_metadata_tool(self, search_server, httpx_mock):
        httpx_mock.add_response(text=ARXIV_ATOM)
        result = _unwrap(await search_server.call_tool(
            "get_paper_metadata",
            {"external_id": "1706.03762", "source": "arxiv"},
        ))
        assert result["external_id"] == "1706.03762"
        assert result["title"] == "Attention Is All You Need"

    async def test_get_paper_metadata_unknown_source(self, search_server):
        result = _unwrap(await search_server.call_tool(
            "get_paper_metadata",
            {"external_id": "anything", "source": "unknown_source"},
        ))
        assert "error" in result

    async def test_get_paper_metadata_not_found(self, search_server, httpx_mock):
        httpx_mock.add_response(
            text='<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        )
        result = _unwrap(await search_server.call_tool(
            "get_paper_metadata",
            {"external_id": "0000.00000", "source": "arxiv"},
        ))
        assert "error" in result


# ---------------------------------------------------------------------------
# PaperKB MCP tools
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPaperKBMCPTools:
    async def test_ingest_paper_tool(self, mcp_server, kb_service, tmp_path):
        fake_text = "Attention mechanism self-attention multi-head. " * 40
        with (
            patch("src.core.kb_service.download_pdf", new=AsyncMock(return_value=tmp_path / "fake.pdf")),
            patch("src.core.kb_service.parse_pdf", return_value=fake_text),
        ):
            result = _unwrap(await mcp_server.call_tool(
                "ingest_paper",
                {
                    "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf",
                    "title": "Attention Is All You Need",
                    "source": "arxiv",
                    "external_id": "1706.03762",
                    "tags": ["transformer"],
                },
            ))
        assert "paper_id" in result
        assert result["num_chunks"] > 0

    async def test_list_kb_papers_empty(self, mcp_server, kb_service):
        result = _unwrap(await mcp_server.call_tool("list_kb_papers", {}))
        assert result == []

    async def test_list_kb_papers_with_data(self, mcp_server, kb_service):
        kb_service._papers.upsert(
            Paper(source="arxiv", external_id="list.001", title="Listed Paper")
        )
        result = _unwrap(await mcp_server.call_tool("list_kb_papers", {}))
        assert len(result) == 1
        assert result[0]["title"] == "Listed Paper"

    async def test_list_kb_papers_tag_filter(self, mcp_server, kb_service):
        pid = kb_service._papers.upsert(
            Paper(source="arxiv", external_id="tag.list.001", title="Tagged Paper")
        )
        kb_service._papers.add_tags(pid, ["nlp"])
        result = _unwrap(await mcp_server.call_tool("list_kb_papers", {"tag": "nlp"}))
        assert any(p["internal_id"] == pid for p in result)

    async def test_search_kb_returns_chunks(self, mcp_server, kb_service):
        pid = kb_service._papers.upsert(
            Paper(source="arxiv", external_id="srch.001", title="Search Test")
        )
        text = "neural network deep learning gradient descent"
        emb = await kb_service._embedder.embed_one(text)
        kb_service._chunks.insert_chunks([
            PaperChunk(paper_id=pid, chunk_index=0, text=text, embedding=emb)
        ])
        result = _unwrap(await mcp_server.call_tool("search_kb", {"query": "deep learning", "top_k": 3}))
        assert isinstance(result, list)
        assert len(result) >= 1
        assert all("score" in item for item in result)

    async def test_qa_over_papers_scoped(self, mcp_server, kb_service):
        p1 = kb_service._papers.upsert(Paper(source="arxiv", external_id="qa.001", title="QA P1"))
        p2 = kb_service._papers.upsert(Paper(source="arxiv", external_id="qa.002", title="QA P2"))
        for pid, text in [(p1, "transformer self attention"), (p2, "decision tree random forest")]:
            emb = await kb_service._embedder.embed_one(text)
            kb_service._chunks.insert_chunks([
                PaperChunk(paper_id=pid, chunk_index=0, text=text, embedding=emb)
            ])
        result = _unwrap(await mcp_server.call_tool(
            "qa_over_papers",
            {"question": "attention mechanism", "paper_ids": [p1], "top_k": 2},
        ))
        assert all(item["paper_id"] == p1 for item in result)

    async def test_qa_over_papers_all_papers(self, mcp_server, kb_service):
        p1 = kb_service._papers.upsert(
            Paper(source="arxiv", external_id="qa.all.001", title="All P1")
        )
        emb = await kb_service._embedder.embed_one("some technical content")
        kb_service._chunks.insert_chunks([
            PaperChunk(paper_id=p1, chunk_index=0, text="some technical content", embedding=emb)
        ])
        result = _unwrap(await mcp_server.call_tool(
            "qa_over_papers",
            {"question": "technical content", "paper_ids": [], "top_k": 5},
        ))
        assert len(result) >= 1

    async def test_tag_paper_tool(self, mcp_server, kb_service):
        pid = kb_service._papers.upsert(
            Paper(source="arxiv", external_id="tag.tool.001", title="Tag Me")
        )
        result = _unwrap(await mcp_server.call_tool(
            "tag_paper",
            {"paper_id": pid, "tags": ["survey", "nlp"]},
        ))
        assert result["paper_id"] == pid
        assert "survey" in result["tags_added"]

        tagged = kb_service._papers.list(tag="survey")
        assert any(p.internal_id == pid for p in tagged)
