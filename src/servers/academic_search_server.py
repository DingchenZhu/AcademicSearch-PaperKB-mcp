"""AcademicSearch MCP Server.

Exposes academic paper discovery capabilities as MCP tools.
Does NOT call any LLM and does NOT write to the KB.

Start via:
    python -m src.servers.academic_search_server
or via the installed script:
    academic-search-server
"""

from __future__ import annotations

import os
from typing import Annotated, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.core.models import Paper
from src.core.paper_search import search_papers
from src.core.paper_search.arxiv_client import ArxivClient

load_dotenv()

mcp = FastMCP(
    name="AcademicSearch",
    instructions=(
        "Tools for discovering academic papers from arXiv and other sources. "
        "Returns structured metadata; does not download PDFs or touch the KB."
    ),
    host="0.0.0.0",
    port=int(os.getenv("ACADEMIC_SEARCH_PORT", "9001")),
    streamable_http_path="/mcp",
)


@mcp.tool()
async def search_papers_tool(
    query: Annotated[str, Field(description="Natural-language or keyword query")],
    year_from: Annotated[Optional[int], Field(description="Earliest publication year (inclusive)")] = None,
    year_to: Annotated[Optional[int], Field(description="Latest publication year (inclusive)")] = None,
    max_results: Annotated[int, Field(description="Max papers to return", ge=1, le=100)] = 20,
    sources: Annotated[
        list[str],
        Field(description='Search backends to use, e.g. ["arxiv"]'),
    ] = ["arxiv"],
) -> list[dict]:
    """Search for academic papers matching *query* and return a ranked list of metadata."""
    papers = await search_papers(
        query=query,
        sources=sources,
        year_from=year_from,
        year_to=year_to,
        max_results=max_results,
    )
    return [p.model_dump(mode="json") for p in papers]


@mcp.tool()
async def get_paper_metadata(
    external_id: Annotated[str, Field(description="arXiv ID, DOI, or source-specific paper ID")],
    source: Annotated[str, Field(description='Source name, e.g. "arxiv"')] = "arxiv",
) -> dict:
    """Fetch full metadata for a single paper by its source-specific ID."""
    clients = {"arxiv": ArxivClient}
    client_cls = clients.get(source)
    if client_cls is None:
        return {"error": f"Unsupported source: {source}"}
    client = client_cls()
    paper = await client.get_metadata(external_id)
    if paper is None:
        return {"error": f"Paper not found: {external_id} in {source}"}
    return paper.model_dump(mode="json")


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
