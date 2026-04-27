"""V3 tests: Semantic Scholar client + aggregator multi-source ranking."""

from __future__ import annotations

import json
import pytest
from pytest_httpx import HTTPXMock

from src.core.models import Paper
from src.core.paper_search.semantic_scholar import SemanticScholarClient, _to_paper
from src.core.paper_search.aggregator import search_papers, _dedup_cross_source, _rank_key, _normalize_title

_SS_API = "https://api.semanticscholar.org/graph/v1"

# ---------------------------------------------------------------------------
# Sample SS response payloads
# ---------------------------------------------------------------------------

SS_ATTENTION = {
    "paperId": "204e3073870fae3d05bcbc2f6a8e263d9b72e776",
    "title": "Attention Is All You Need",
    "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.",
    "authors": [{"authorId": "1", "name": "Ashish Vaswani"}, {"authorId": "2", "name": "Noam Shazeer"}],
    "year": 2017,
    "venue": "NeurIPS",
    "citationCount": 80000,
    "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762.pdf", "status": "GREEN"},
    "externalIds": {"ArXiv": "1706.03762"},
}

SS_GPT3 = {
    "paperId": "gpt3_paper_id",
    "title": "Language Models are Few-Shot Learners",
    "abstract": "We demonstrate that scaling language models greatly improves few-shot performance.",
    "authors": [{"authorId": "3", "name": "Tom B. Brown"}],
    "year": 2020,
    "venue": "NeurIPS",
    "citationCount": 40000,
    "openAccessPdf": None,
    "externalIds": {},
}

SS_RESPONSE = {"total": 2, "data": [SS_ATTENTION, SS_GPT3]}
SS_EMPTY = {"total": 0, "data": []}


# ---------------------------------------------------------------------------
# Unit tests: _to_paper
# ---------------------------------------------------------------------------

class TestToPaper:
    def test_basic_fields(self):
        p = _to_paper(SS_ATTENTION)
        assert p.source == "semantic_scholar"
        assert p.external_id == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
        assert p.title == "Attention Is All You Need"
        assert p.year == 2017
        assert p.citations == 80000
        assert "Vaswani" in p.authors[0]
        assert p.url_pdf == "https://arxiv.org/pdf/1706.03762.pdf"

    def test_pdf_url_fallback_to_arxiv(self):
        item = {**SS_ATTENTION, "openAccessPdf": None}
        p = _to_paper(item)
        assert p.url_pdf == "https://arxiv.org/pdf/1706.03762.pdf"

    def test_no_pdf_url_when_no_open_access_no_arxiv(self):
        p = _to_paper(SS_GPT3)
        assert p.url_pdf == ""

    def test_none_citation_count(self):
        item = {**SS_ATTENTION, "citationCount": None}
        p = _to_paper(item)
        assert p.citations is None

    def test_missing_abstract(self):
        item = {**SS_ATTENTION, "abstract": None}
        p = _to_paper(item)
        assert p.abstract == ""


# ---------------------------------------------------------------------------
# Integration tests: SemanticScholarClient with httpx mock
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSemanticScholarClientMocked:
    async def test_search_returns_papers(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=json.dumps(SS_RESPONSE))
        client = SemanticScholarClient()
        papers = await client.search("transformer")
        assert len(papers) == 2
        assert papers[0].title == "Attention Is All You Need"

    async def test_search_empty_result(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=json.dumps(SS_EMPTY))
        client = SemanticScholarClient()
        papers = await client.search("zzznonsense")
        assert papers == []

    async def test_get_metadata_found(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=json.dumps(SS_ATTENTION))
        client = SemanticScholarClient()
        paper = await client.get_metadata("204e3073870fae3d05bcbc2f6a8e263d9b72e776")
        assert paper is not None
        assert paper.citations == 80000

    async def test_get_metadata_not_found(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(status_code=404)
        client = SemanticScholarClient()
        paper = await client.get_metadata("nonexistent_id")
        assert paper is None

    @pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
    async def test_http_error_retries(self, httpx_mock: HTTPXMock):
        for _ in range(3):
            httpx_mock.add_response(status_code=500)
        client = SemanticScholarClient()
        with pytest.raises(Exception):
            await client.search("test")


# ---------------------------------------------------------------------------
# Unit tests: aggregator helpers
# ---------------------------------------------------------------------------

class TestAggregatorHelpers:
    def test_normalize_title(self):
        t = _normalize_title("Attention Is ALL You Need!!")
        assert t == "attention is all you need"

    def test_rank_key_citations_first(self):
        high = Paper(source="arxiv", external_id="a", title="A", citations=1000, year=2020)
        low  = Paper(source="arxiv", external_id="b", title="B", citations=10,   year=2022)
        assert _rank_key(high) < _rank_key(low)  # high citations → smaller key → sorted first

    def test_rank_key_year_tiebreaker(self):
        newer = Paper(source="arxiv", external_id="a", title="A", citations=None, year=2023)
        older = Paper(source="arxiv", external_id="b", title="B", citations=None, year=2019)
        assert _rank_key(newer) < _rank_key(older)

    def test_rank_key_source_tiebreaker(self):
        arxiv = Paper(source="arxiv",            external_id="a", title="A", citations=100, year=2021)
        ss    = Paper(source="semantic_scholar", external_id="b", title="A", citations=100, year=2021)
        assert _rank_key(arxiv) < _rank_key(ss)

    def test_rank_key_none_citations_last(self):
        with_cit    = Paper(source="arxiv", external_id="a", title="A", citations=1, year=2020)
        without_cit = Paper(source="arxiv", external_id="b", title="B", citations=None, year=2020)
        assert _rank_key(with_cit) < _rank_key(without_cit)


class TestCrossSourceDedup:
    def _make_papers(self):
        arxiv = Paper(source="arxiv", external_id="1706.03762",
                      title="Attention Is All You Need", year=2017, citations=80000,
                      url_pdf="https://arxiv.org/pdf/1706.03762.pdf")
        ss    = Paper(source="semantic_scholar", external_id="ss_id_abc",
                      title="Attention Is All You Need", year=2017, citations=79000, url_pdf="")
        unique= Paper(source="arxiv", external_id="2005.14165",
                      title="Language Models are Few-Shot Learners", year=2020, citations=40000)
        return arxiv, ss, unique

    def test_dedup_removes_same_title_year(self):
        arxiv, ss, unique = self._make_papers()
        result = _dedup_cross_source([arxiv, ss, unique])
        titles = [p.title for p in result]
        assert titles.count("Attention Is All You Need") == 1

    def test_dedup_keeps_richer_entry(self):
        arxiv, ss, _ = self._make_papers()
        result = _dedup_cross_source([ss, arxiv])  # ss first, arxiv richer
        kept = next(p for p in result if p.title == "Attention Is All You Need")
        assert kept.citations == 80000  # arxiv has higher citations

    def test_dedup_different_titles_kept(self):
        arxiv, _, unique = self._make_papers()
        result = _dedup_cross_source([arxiv, unique])
        assert len(result) == 2

    def test_dedup_case_insensitive(self):
        p1 = Paper(source="arxiv", external_id="a1", title="BERT: Pre-training", year=2019, citations=50000)
        p2 = Paper(source="semantic_scholar", external_id="b1", title="bert: pre-training", year=2019, citations=49000)
        result = _dedup_cross_source([p1, p2])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration tests: multi-source aggregator
# ---------------------------------------------------------------------------

ARXIV_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>We propose the Transformer.</summary>
    <author><name>Ashish Vaswani</name></author>
    <published>2017-06-12T00:00:00Z</published>
  </entry>
</feed>
"""

@pytest.mark.asyncio
class TestAggregatorMultiSource:
    async def test_multi_source_returns_merged(self, httpx_mock: HTTPXMock):
        # arXiv returns Attention paper; SS returns GPT-3
        httpx_mock.add_response(text=ARXIV_ATOM)   # arXiv
        httpx_mock.add_response(text=json.dumps({"total": 1, "data": [SS_GPT3]}))  # SS
        papers = await search_papers("model", sources=["arxiv", "semantic_scholar"], max_results=5)
        titles = {p.title for p in papers}
        assert "Attention Is All You Need" in titles
        assert "Language Models are Few-Shot Learners" in titles

    async def test_sorted_by_citations(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(text=json.dumps(SS_RESPONSE))
        papers = await search_papers("transformer", sources=["semantic_scholar"], max_results=5)
        citations = [p.citations or -1 for p in papers]
        assert citations == sorted(citations, reverse=True)

    async def test_cross_source_dedup_applied(self, httpx_mock: HTTPXMock):
        # Both sources return "Attention Is All You Need"
        httpx_mock.add_response(text=ARXIV_ATOM)
        httpx_mock.add_response(text=json.dumps({"total": 1, "data": [SS_ATTENTION]}))
        papers = await search_papers("attention", sources=["arxiv", "semantic_scholar"], max_results=10)
        attention_count = sum(1 for p in papers if "Attention" in p.title)
        assert attention_count == 1, "cross-source duplicate not removed"
