"""REST API layer (V3) — decoupled from MCP server modules.

Mirrors all MCP tool functionality over HTTP for environments that don't
support MCP (LangChain Tools, Langflow HTTP nodes, etc.).

Run with:
    uvicorn src.api.app:app --port 8000
or:
    rest-api-server
"""

from __future__ import annotations

import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.kb_service import get_kb_service
from src.core.paper_search import search_papers

load_dotenv()

app = FastAPI(
    title="AcademicSearch + PaperKB REST API",
    description="HTTP interface for the academic search and paper KB core library.",
    version="0.3.0",
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    sources: list[str] = ["arxiv"]
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    max_results: int = 20


class IngestRequest(BaseModel):
    pdf_url: str
    title: str = ""
    source: str = "manual"
    external_id: str = ""
    tags: list[str] = []


class SearchKBRequest(BaseModel):
    query: str
    top_k: int = 5


class QARequest(BaseModel):
    question: str
    paper_ids: list[str] = []
    top_k: int = 5


class TagRequest(BaseModel):
    paper_id: str
    tags: list[str]


class ListPapersRequest(BaseModel):
    query: Optional[str] = None
    tag: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------

@app.post("/api/search_papers", tags=["search"])
async def api_search_papers(req: SearchRequest) -> list[dict]:
    """Search external academic sources (arXiv, Semantic Scholar, …)."""
    papers = await search_papers(
        query=req.query,
        sources=req.sources,
        year_from=req.year_from,
        year_to=req.year_to,
        max_results=req.max_results,
    )
    return [p.model_dump(mode="json") for p in papers]


# ---------------------------------------------------------------------------
# KB endpoints
# ---------------------------------------------------------------------------

@app.post("/api/ingest_paper", tags=["kb"])
async def api_ingest_paper(req: IngestRequest) -> dict:
    """Download and ingest a PDF into the knowledge base."""
    result = await get_kb_service().ingest_paper(
        pdf_url=req.pdf_url,
        title=req.title,
        source=req.source,
        external_id=req.external_id,
        tags=req.tags,
    )
    return result.model_dump()


@app.post("/api/list_papers", tags=["kb"])
async def api_list_papers(req: ListPapersRequest) -> list[dict]:
    """List papers in the KB with optional filters."""
    papers = get_kb_service().list_papers(
        query=req.query,
        tag=req.tag,
        year_from=req.year_from,
        year_to=req.year_to,
    )
    return [p.model_dump(mode="json") for p in papers]


@app.post("/api/search_kb", tags=["kb"])
async def api_search_kb(req: SearchKBRequest) -> list[dict]:
    """Vector-search the KB and return the most relevant chunks."""
    results = await get_kb_service().search_kb(req.query, top_k=req.top_k)
    return [r.model_dump() for r in results]


@app.post("/api/qa_over_papers", tags=["kb"])
async def api_qa_over_papers(req: QARequest) -> list[dict]:
    """Retrieve context chunks for a question, optionally scoped to specific papers."""
    pid_filter = req.paper_ids if req.paper_ids else None
    results = await get_kb_service().search_kb(
        req.question, top_k=req.top_k, paper_ids=pid_filter
    )
    return [r.model_dump() for r in results]


@app.post("/api/tag_paper", tags=["kb"])
async def api_tag_paper(req: TagRequest) -> dict:
    """Add tags to a paper in the KB."""
    get_kb_service().tag_paper(req.paper_id, req.tags)
    return {"paper_id": req.paper_id, "tags_added": req.tags}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    port = int(os.getenv("REST_API_PORT", "8000"))
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
