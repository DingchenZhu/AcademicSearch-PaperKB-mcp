"""Semantic Scholar Graph API client.

Free tier (no key): 100 req/5 min.
With SEMANTIC_SCHOLAR_API_KEY: 1 req/s (higher limits negotiable).

Docs: https://api.semanticscholar.org/api-docs/graph
"""

from __future__ import annotations

import os
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.models import Paper
from .base import BaseSearchClient

_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,title,abstract,authors,year,venue,citationCount,openAccessPdf,externalIds"


class SemanticScholarClient(BaseSearchClient):
    """Semantic Scholar Graph API client."""

    def __init__(self, timeout: float = 20.0) -> None:
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        headers = {"x-api-key": api_key} if api_key else {}
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_results: int = 20,
    ) -> list[Paper]:
        params: dict = {
            "query": query,
            "fields": _FIELDS,
            "limit": min(max_results, 100),
        }
        if year_from or year_to:
            lo = str(year_from) if year_from else "1900"
            hi = str(year_to) if year_to else "2100"
            params["year"] = f"{lo}-{hi}"

        resp = await self._client.get(f"{_BASE}/paper/search", params=params)
        resp.raise_for_status()
        data = resp.json()
        return [_to_paper(item) for item in data.get("data", [])]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_metadata(self, external_id: str) -> Optional[Paper]:
        resp = await self._client.get(
            f"{_BASE}/paper/{external_id}",
            params={"fields": _FIELDS},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _to_paper(resp.json())

    async def aclose(self) -> None:
        await self._client.aclose()


def _to_paper(item: dict) -> Paper:
    authors = [a.get("name", "") for a in item.get("authors", [])]
    pdf_info = item.get("openAccessPdf") or {}
    url_pdf = pdf_info.get("url", "")

    # Prefer arXiv PDF URL when available
    ext_ids = item.get("externalIds") or {}
    arxiv_id = ext_ids.get("ArXiv")
    if not url_pdf and arxiv_id:
        url_pdf = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    return Paper(
        source="semantic_scholar",
        external_id=item.get("paperId", ""),
        title=(item.get("title") or "").strip(),
        abstract=(item.get("abstract") or "").strip(),
        authors=authors,
        year=item.get("year"),
        venue=(item.get("venue") or "").strip(),
        url_pdf=url_pdf,
        citations=item.get("citationCount"),
    )
