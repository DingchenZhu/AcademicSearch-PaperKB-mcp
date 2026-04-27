"""V0 tests: arXiv search (unit + httpx-mocked integration)."""

import pytest
from pytest_httpx import HTTPXMock

from src.core.paper_search.arxiv_client import ArxivClient, _parse_atom
from src.core.paper_search.aggregator import search_papers

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ATTENTION_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>We propose a new simple network architecture, the Transformer,
    based solely on attention mechanisms.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    <published>2017-06-12T17:57:34Z</published>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>
"""

MULTI_ATOM = ATTENTION_ATOM.replace(
    "</feed>",
    """\
  <entry>
    <id>http://arxiv.org/abs/2005.14165v4</id>
    <title>Language Models are Few-Shot Learners</title>
    <summary>We demonstrate that scaling language models greatly improves few-shot performance.</summary>
    <author><name>Tom B. Brown</name></author>
    <published>2020-05-28T17:12:13Z</published>
  </entry>
</feed>""",
)

EMPTY_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>
"""

# ---------------------------------------------------------------------------
# Unit tests: _parse_atom
# ---------------------------------------------------------------------------

class TestParseAtom:
    def test_single_entry(self):
        papers = _parse_atom(ATTENTION_ATOM)
        assert len(papers) == 1
        p = papers[0]
        assert p.source == "arxiv"
        assert p.external_id == "1706.03762"
        assert p.title == "Attention Is All You Need"
        assert p.year == 2017
        assert "Vaswani" in p.authors[0]
        assert len(p.authors) == 3
        assert p.url_pdf == "https://arxiv.org/pdf/1706.03762.pdf"
        assert "Transformer" in p.abstract

    def test_multiple_entries(self):
        papers = _parse_atom(MULTI_ATOM)
        assert len(papers) == 2
        ids = {p.external_id for p in papers}
        assert "1706.03762" in ids
        assert "2005.14165" in ids

    def test_empty_feed(self):
        assert _parse_atom(EMPTY_ATOM) == []

    def test_version_suffix_stripped(self):
        atom = ATTENTION_ATOM.replace("1706.03762v5", "1706.03762v99")
        papers = _parse_atom(atom)
        assert papers[0].external_id == "1706.03762"

    def test_internal_id_is_uuid(self):
        papers = _parse_atom(ATTENTION_ATOM)
        import uuid
        uuid.UUID(papers[0].internal_id)  # raises if not valid UUID


# ---------------------------------------------------------------------------
# Integration tests: ArxivClient with httpx mock
# ---------------------------------------------------------------------------

ARXIV_API = "https://export.arxiv.org/api/query"


@pytest.mark.asyncio
class TestArxivClientMocked:
    # pytest_httpx matches exact URL (incl. query params) by default.
    # Omitting `url=` makes the mock catch any request from this test.

    async def test_search_returns_papers(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=ATTENTION_ATOM)
        client = ArxivClient()
        papers = await client.search("attention transformer", max_results=1)
        assert len(papers) == 1
        assert papers[0].external_id == "1706.03762"

    async def test_search_with_year_filter(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=MULTI_ATOM)
        client = ArxivClient()
        papers = await client.search("language model", year_from=2020, year_to=2021, max_results=10)
        assert len(papers) == 2

    async def test_get_metadata(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=ATTENTION_ATOM)
        client = ArxivClient()
        paper = await client.get_metadata("1706.03762")
        assert paper is not None
        assert paper.title == "Attention Is All You Need"

    async def test_get_metadata_not_found(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=EMPTY_ATOM)
        client = ArxivClient()
        paper = await client.get_metadata("0000.00000")
        assert paper is None

    # tenacity retries 3 times: register 3 error responses + allow any leftovers
    @pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
    async def test_http_error_propagates(self, httpx_mock: HTTPXMock):
        for _ in range(3):
            httpx_mock.add_response(status_code=503)
        client = ArxivClient()
        with pytest.raises(Exception):
            await client.search("test")


# ---------------------------------------------------------------------------
# Integration tests: aggregator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAggregator:
    async def test_search_papers_deduplicates(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=ATTENTION_ATOM)
        papers = await search_papers("transformer", sources=["arxiv"], max_results=5)
        external_ids = [p.external_id for p in papers]
        assert len(external_ids) == len(set(external_ids)), "duplicates found"

    async def test_search_papers_unknown_source_skipped(self):
        papers = await search_papers("x", sources=["nonexistent_source"], max_results=5)
        assert papers == []

    async def test_search_papers_respects_max_results(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=MULTI_ATOM)
        papers = await search_papers("x", sources=["arxiv"], max_results=1)
        assert len(papers) <= 1
