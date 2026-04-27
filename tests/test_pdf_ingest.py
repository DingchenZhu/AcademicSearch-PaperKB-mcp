"""Unit tests for pdf_ingest.chunker."""

from src.core.pdf_ingest.chunker import chunk_text


def test_chunk_text_basic():
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) > 1
    # First chunk length
    assert len(chunks[0]) == 1000
    # Adjacent chunks overlap by ~100 chars
    assert chunks[0][-100:] == chunks[1][:100]


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short():
    text = "hello world"
    chunks = chunk_text(text, chunk_size=1000)
    assert chunks == [text]
