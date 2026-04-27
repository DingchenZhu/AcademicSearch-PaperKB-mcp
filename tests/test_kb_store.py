"""Integration tests for kb_store (uses in-memory SQLite)."""

import pytest
from src.core.kb_store.database import init_db
from src.core.kb_store.paper_store import PaperStore
from src.core.kb_store.chunk_store import ChunkStore
from src.core.models import Paper, PaperChunk
from pathlib import Path


@pytest.fixture
def stores(tmp_path):
    conn = init_db(tmp_path / "test.sqlite")
    return PaperStore(conn), ChunkStore(conn)


def test_upsert_and_get_paper(stores):
    ps, _ = stores
    paper = Paper(source="arxiv", external_id="1234.5678", title="Test Paper")
    pid = ps.upsert(paper)
    assert pid
    fetched = ps.get(pid)
    assert fetched is not None
    assert fetched.title == "Test Paper"


def test_upsert_is_idempotent(stores):
    ps, _ = stores
    paper = Paper(source="arxiv", external_id="0000.0001", title="Duplicate")
    pid1 = ps.upsert(paper)
    pid2 = ps.upsert(paper)
    assert pid1 == pid2


def test_add_and_list_by_tag(stores):
    ps, _ = stores
    paper = Paper(source="arxiv", external_id="2222.3333", title="Tagged Paper")
    pid = ps.upsert(paper)
    ps.add_tags(pid, ["ml", "nlp"])
    results = ps.list(tag="ml")
    assert any(p.internal_id == pid for p in results)
    results_no_match = ps.list(tag="physics")
    assert not any(p.internal_id == pid for p in results_no_match)


def test_insert_and_retrieve_chunks(stores):
    ps, cs = stores
    paper = Paper(source="arxiv", external_id="3333.4444", title="Chunk Test")
    pid = ps.upsert(paper)
    chunks = [
        PaperChunk(paper_id=pid, chunk_index=i, text=f"chunk {i}", embedding=[0.1, 0.2, 0.3])
        for i in range(3)
    ]
    cs.insert_chunks(chunks)
    fetched = cs.get_chunks_by_paper(pid)
    assert len(fetched) == 3
    assert fetched[0].text == "chunk 0"
    assert fetched[0].embedding == pytest.approx([0.1, 0.2, 0.3], abs=1e-5)
