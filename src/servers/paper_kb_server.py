"""PaperKB MCP Server.

Exposes paper knowledge-base lifecycle operations as MCP tools:
  ingest_paper, list_kb_papers, search_kb, qa_over_papers, tag_paper.

Does NOT call any LLM for answer generation — only returns context chunks.

Start via:
    python -m src.servers.paper_kb_server
or:
    paper-kb-server
"""

from __future__ import annotations

import os
from typing import Annotated, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from src.core.kb_service import get_kb_service

load_dotenv()

mcp = FastMCP(
    name="PaperKB",
    instructions=(
        "Tools for managing a local paper knowledge base: ingest PDFs, list stored papers, "
        "run vector search, and retrieve context chunks for downstream QA."
    ),
    host="0.0.0.0",
    port=int(os.getenv("PAPER_KB_PORT", "9002")),
    streamable_http_path="/mcp",
)


@mcp.tool()
async def ingest_paper(
    pdf_url: Annotated[str, Field(description="Direct URL to a PDF file")],
    title: Annotated[str, Field(description="Paper title")] = "",
    source: Annotated[str, Field(description='Source name, e.g. "arxiv"')] = "manual",
    external_id: Annotated[str, Field(description="Source-specific paper ID")] = "",
    tags: Annotated[list[str], Field(description="Optional tags to attach")] = [],
) -> dict:
    """Download, parse, chunk, embed, and store a paper PDF in the knowledge base."""
    result = await get_kb_service().ingest_paper(
        pdf_url=pdf_url,
        title=title,
        source=source,
        external_id=external_id,
        tags=tags,
    )
    return result.model_dump()


@mcp.tool()
async def list_kb_papers(
    query: Annotated[Optional[str], Field(description="Title/abstract keyword filter")] = None,
    tag: Annotated[Optional[str], Field(description="Filter by tag")] = None,
    year_from: Annotated[Optional[int], Field(description="Earliest year")] = None,
    year_to: Annotated[Optional[int], Field(description="Latest year")] = None,
) -> list[dict]:
    """List papers stored in the knowledge base, with optional filters."""
    papers = get_kb_service().list_papers(
        query=query, tag=tag, year_from=year_from, year_to=year_to
    )
    return [p.model_dump(mode="json") for p in papers]


@mcp.tool()
async def search_kb(
    query: Annotated[str, Field(description="Semantic search query")],
    top_k: Annotated[int, Field(description="Number of chunks to return", ge=1, le=50)] = 5,
) -> list[dict]:
    """Vector-search all embedded chunks and return the most relevant results."""
    results = await get_kb_service().search_kb(query, top_k=top_k)
    return [r.model_dump() for r in results]


@mcp.tool()
async def qa_over_papers(
    question: Annotated[str, Field(description="Question to answer using stored papers")],
    paper_ids: Annotated[
        list[str],
        Field(description="Limit search to these paper IDs; empty = all papers"),
    ] = [],
    top_k: Annotated[int, Field(description="Number of context chunks to return", ge=1, le=50)] = 5,
) -> list[dict]:
    """Retrieve the most relevant chunks for *question* from the specified papers.

    Returns context chunks only — the MCP host's LLM is responsible for
    generating the final answer from these chunks.
    """
    pid_filter = paper_ids if paper_ids else None
    results = await get_kb_service().search_kb(question, top_k=top_k, paper_ids=pid_filter)
    return [r.model_dump() for r in results]


@mcp.tool()
async def tag_paper(
    paper_id: Annotated[str, Field(description="Internal paper UUID")],
    tags: Annotated[list[str], Field(description="Tags to add")],
) -> dict:
    """Add one or more tags to a paper already stored in the KB."""
    get_kb_service().tag_paper(paper_id, tags)
    return {"paper_id": paper_id, "tags_added": tags}


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
