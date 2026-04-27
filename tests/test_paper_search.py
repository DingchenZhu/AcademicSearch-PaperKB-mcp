"""Unit tests for paper_search / arxiv_client."""

import pytest
from unittest.mock import AsyncMock, patch

from src.core.models import Paper
from src.core.paper_search.arxiv_client import ArxivClient, _parse_atom


SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>We propose a new simple network architecture, the Transformer.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <published>2017-06-12T00:00:00Z</published>
  </entry>
</feed>"""


def test_parse_atom_returns_paper():
    papers = _parse_atom(SAMPLE_ATOM)
    assert len(papers) == 1
    p = papers[0]
    assert p.source == "arxiv"
    assert p.external_id == "1706.03762"
    assert "Vaswani" in p.authors[0]
    assert p.year == 2017
    assert p.url_pdf == "https://arxiv.org/pdf/1706.03762.pdf"


def test_parse_atom_empty_feed():
    empty = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    assert _parse_atom(empty) == []
