"""Aggregate, deduplicate, and rank results from multiple search backends."""

from __future__ import annotations

import re
from typing import Optional

from src.core.models import Paper
from .arxiv_client import ArxivClient
from .semantic_scholar import SemanticScholarClient

# Source priority used as final tiebreaker (lower = preferred)
_SOURCE_PRIORITY = {"arxiv": 0, "semantic_scholar": 1}

# Registry: extend here to add new backends
_CLIENTS: dict[str, type] = {
    "arxiv": ArxivClient,
    "semantic_scholar": SemanticScholarClient,
}


async def search_papers(
    query: str,
    sources: list[str] | None = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    max_results: int = 20,
) -> list[Paper]:
    """Search across one or more backends, deduplicate across sources, and rank results.

    Ranking priority:
      1. Citation count descending (None treated as -1, goes last)
      2. Publication year descending (None treated as 0)
      3. Source priority (arXiv before Semantic Scholar)

    Deduplication:
      - (source, external_id) exact dedup within a source
      - Normalized-title + year fuzzy dedup across sources (keeps the richer entry)
    """
    if sources is None:
        sources = ["arxiv"]

    all_papers: list[Paper] = []
    seen_keys: set[tuple[str, str]] = set()  # (source, external_id)

    for source in sources:
        client_cls = _CLIENTS.get(source)
        if client_cls is None:
            continue
        client = client_cls()
        papers = await client.search(
            query, year_from=year_from, year_to=year_to, max_results=max_results
        )
        for paper in papers:
            key = (paper.source, paper.external_id)
            if key not in seen_keys:
                seen_keys.add(key)
                all_papers.append(paper)

    # Cross-source dedup by normalised title + year
    deduplicated = _dedup_cross_source(all_papers)

    # Rank by citations → year → source priority
    deduplicated.sort(key=_rank_key)

    return deduplicated[:max_results]


def _rank_key(p: Paper) -> tuple:
    citations = p.citations if p.citations is not None else -1
    year = p.year if p.year is not None else 0
    priority = _SOURCE_PRIORITY.get(p.source, 99)
    return (-citations, -year, priority)


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _dedup_cross_source(papers: list[Paper]) -> list[Paper]:
    """Remove cross-source duplicates, keeping the entry with more information."""
    seen_titles: dict[str, Paper] = {}   # normalised_title+year → best Paper
    result: list[Paper] = []

    for paper in papers:
        norm = _normalize_title(paper.title)
        title_key = f"{norm}|{paper.year or ''}"

        if title_key in seen_titles:
            # Keep whichever has more info: prefer higher citations, then has pdf URL
            existing = seen_titles[title_key]
            existing_score = (existing.citations or -1, bool(existing.url_pdf))
            new_score = (paper.citations or -1, bool(paper.url_pdf))
            if new_score > existing_score:
                # Replace existing in result list
                idx = result.index(existing)
                result[idx] = paper
                seen_titles[title_key] = paper
        else:
            seen_titles[title_key] = paper
            result.append(paper)

    return result
