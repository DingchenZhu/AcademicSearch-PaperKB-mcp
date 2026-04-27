"""arXiv search client using the public Atom API (no API key required)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.models import Paper
from .base import BaseSearchClient

_ARXIV_API = "https://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


class ArxivClient(BaseSearchClient):
    def __init__(self, timeout: float = 20.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_results: int = 20,
    ) -> list[Paper]:
        search_query = query
        if year_from or year_to:
            lo = str(year_from) if year_from else "0000"
            hi = str(year_to) if year_to else "9999"
            # arXiv date filter in the form submittedDate:[YYYYMMDD000000 TO YYYYMMDD235959]
            search_query = (
                f"({query}) AND submittedDate:[{lo}0101000000 TO {hi}1231235959]"
            )

        params = {
            "search_query": f"all:{search_query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        resp = await self._client.get(_ARXIV_API, params=params)
        resp.raise_for_status()
        return _parse_atom(resp.text)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_metadata(self, external_id: str) -> Optional[Paper]:
        params = {"id_list": external_id, "max_results": 1}
        resp = await self._client.get(_ARXIV_API, params=params)
        resp.raise_for_status()
        papers = _parse_atom(resp.text)
        return papers[0] if papers else None

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse_atom(xml_text: str) -> list[Paper]:
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", _NS):
        raw_id = (entry.findtext("atom:id", "", _NS) or "").strip()
        # e.g. http://arxiv.org/abs/2101.00001v2  →  2101.00001
        arxiv_id = re.sub(r"v\d+$", "", raw_id.split("/abs/")[-1])
        title = (entry.findtext("atom:title", "", _NS) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", "", _NS) or "").replace("\n", " ").strip()
        authors = [
            a.findtext("atom:name", "", _NS) or ""
            for a in entry.findall("atom:author", _NS)
        ]
        published = entry.findtext("atom:published", "", _NS) or ""
        year = int(published[:4]) if published else None
        url_pdf = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        papers.append(
            Paper(
                source="arxiv",
                external_id=arxiv_id,
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                url_pdf=url_pdf,
            )
        )
    return papers
