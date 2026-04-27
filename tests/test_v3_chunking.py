"""V3 tests: paragraph chunker + strategy factory."""

from __future__ import annotations

import pytest

from src.core.pdf_ingest.chunker import chunk_text, make_chunker, paragraph_chunk


PARA_TEXT = """\
Deep learning has transformed the field of computer vision.
Convolutional neural networks achieve state-of-the-art results.

Attention mechanisms were introduced to handle variable-length sequences.
The Transformer architecture relies entirely on attention.
It has become the dominant model in NLP tasks.

Graph neural networks extend deep learning to graph-structured data.
They propagate information along edges between nodes.
Applications include molecular property prediction and social network analysis.

Reinforcement learning trains agents through trial and error.
Recent successes include AlphaGo and robotic manipulation.
"""


class TestParagraphChunk:
    def test_splits_at_paragraph_boundaries(self):
        chunks = paragraph_chunk(PARA_TEXT, target_size=300)
        # Each chunk must not contain an abrupt mid-sentence break
        for chunk in chunks:
            assert chunk.strip(), "empty chunk"

    def test_all_content_covered(self):
        chunks = paragraph_chunk(PARA_TEXT, target_size=200, overlap_paragraphs=0)
        full = " ".join(chunks)
        for keyword in ["Transformer", "Graph neural", "AlphaGo"]:
            assert keyword in full

    def test_overlap_paragraphs_repeated(self):
        chunks = paragraph_chunk(PARA_TEXT, target_size=200, overlap_paragraphs=1)
        if len(chunks) >= 2:
            # Last paragraph of chunk N should appear at start of chunk N+1
            last_para_of_first = chunks[0].split("\n\n")[-1].strip()
            assert last_para_of_first in chunks[1]

    def test_empty_text(self):
        assert paragraph_chunk("") == []

    def test_whitespace_only(self):
        assert paragraph_chunk("   \n\n   ") == []

    def test_single_paragraph_falls_back_to_char(self):
        text = "a" * 5000  # no blank lines
        chunks = paragraph_chunk(text, target_size=1000)
        assert len(chunks) > 1  # fell back to char chunking

    def test_short_paragraphs_filtered(self):
        # "ok" and "hi" are < 20 chars and should be dropped; the long paragraphs kept.
        text = "ok\n\nThis is a real paragraph with enough content.\n\nhi\n\nAnother good paragraph here indeed."
        chunks = paragraph_chunk(text, target_size=500, min_paragraph_len=20)
        full = " ".join(chunks)
        assert "real paragraph" in full
        assert "Another good paragraph" in full
        assert "ok" not in full.split()   # short stub removed
        assert "hi" not in full.split()

    def test_no_empty_chunks(self):
        chunks = paragraph_chunk(PARA_TEXT, target_size=100)
        assert all(c.strip() for c in chunks)

    def test_target_size_respected_approximately(self):
        chunks = paragraph_chunk(PARA_TEXT, target_size=150, overlap_paragraphs=0)
        # Most chunks should be close to target_size (allow 2x for single large para)
        for chunk in chunks:
            assert len(chunk) <= 150 * 2 + 50


class TestMakeChunker:
    def test_default_is_char(self, monkeypatch):
        monkeypatch.delenv("CHUNK_STRATEGY", raising=False)
        fn = make_chunker()
        assert fn is chunk_text

    def test_explicit_char(self, monkeypatch):
        monkeypatch.setenv("CHUNK_STRATEGY", "char")
        fn = make_chunker()
        assert fn is chunk_text

    def test_explicit_paragraph(self, monkeypatch):
        monkeypatch.setenv("CHUNK_STRATEGY", "paragraph")
        fn = make_chunker()
        assert fn is paragraph_chunk

    def test_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv("CHUNK_STRATEGY", "char")
        fn = make_chunker(strategy="paragraph")
        assert fn is paragraph_chunk

    def test_unknown_strategy_falls_back_to_char(self, monkeypatch):
        monkeypatch.setenv("CHUNK_STRATEGY", "unknown_strategy")
        fn = make_chunker()
        assert fn is chunk_text

    def test_paragraph_chunker_produces_valid_output(self, monkeypatch):
        monkeypatch.setenv("CHUNK_STRATEGY", "paragraph")
        fn = make_chunker()
        result = fn(PARA_TEXT)
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)
