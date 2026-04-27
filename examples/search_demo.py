"""V0 demo: search arXiv and print results."""

import asyncio
from src.core.paper_search import search_papers


async def main():
    papers = await search_papers(
        query="graph transformer neural network",
        sources=["arxiv"],
        year_from=2021,
        year_to=2024,
        max_results=5,
    )
    for p in papers:
        print(f"[{p.year}] {p.title}")
        print(f"  authors : {', '.join(p.authors[:3])}")
        print(f"  pdf     : {p.url_pdf}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
