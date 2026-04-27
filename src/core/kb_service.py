"""KBService: orchestrates the paper ingest + retrieval pipeline.

Both the MCP server and the REST API use this class directly, so neither
depends on the other. The MCP server's tool handlers delegate to KBService;
the REST API's endpoint handlers do the same.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from src.core.embedding.base import BaseEmbedder
from src.core.kb_query.factory import make_retriever
from src.core.kb_store.chunk_store import ChunkStore
from src.core.kb_store.database import init_db
from src.core.kb_store.paper_store import PaperStore
from src.core.models import IngestResult, Paper, PaperChunk, RetrievedChunk
from src.core.pdf_ingest import download_pdf, make_chunker, parse_pdf


class KBService:
    """High-level operations over the paper knowledge base."""

    def __init__(
        self,
        paper_store: PaperStore,
        chunk_store: ChunkStore,
        embedder: BaseEmbedder,
        chunk_strategy: str = "char",
    ) -> None:
        self._papers = paper_store
        self._chunks = chunk_store
        self._embedder = embedder
        self._retriever = make_retriever(chunk_store, embedder)
        self._chunker = make_chunker(chunk_strategy)

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    async def ingest_paper(
        self,
        pdf_url: str,
        title: str = "",
        source: str = "manual",
        external_id: str = "",
        tags: list[str] | None = None,
    ) -> IngestResult:
        """Download, parse, chunk, embed, and store a paper."""
        paper = Paper(
            source=source,
            external_id=external_id or pdf_url,
            title=title or pdf_url,
            url_pdf=pdf_url,
        )
        paper_id = self._papers.upsert(paper)
        if tags:
            self._papers.add_tags(paper_id, tags)

        pdf_path = await download_pdf(pdf_url)
        text = parse_pdf(pdf_path)
        raw_chunks = self._chunker(text)

        chunks = [
            PaperChunk(paper_id=paper_id, chunk_index=i, text=c)
            for i, c in enumerate(raw_chunks)
        ]

        batch_size = 64
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings = await self._embedder.embed([c.text for c in batch])
            for chunk, emb in zip(batch, embeddings):
                chunk.embedding = emb

        self._chunks.insert_chunks(chunks)

        return IngestResult(
            paper_id=paper_id,
            num_chunks=len(chunks),
            char_count=len(text),
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_papers(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> list[Paper]:
        return self._papers.list(query=query, tag=tag, year_from=year_from, year_to=year_to)

    async def search_kb(
        self,
        query: str,
        top_k: int = 5,
        paper_ids: Optional[list[str]] = None,
    ) -> list[RetrievedChunk]:
        return await self._retriever.search(query, top_k=top_k, paper_ids=paper_ids)

    def tag_paper(self, paper_id: str, tags: list[str]) -> None:
        self._papers.add_tags(paper_id, tags)


# ---------------------------------------------------------------------------
# Module-level singleton for server / API use
# ---------------------------------------------------------------------------

_service: Optional[KBService] = None


def get_kb_service(db_path: Optional[Path] = None) -> KBService:
    """Return (and lazily initialise) the module-level KBService singleton.

    Uses OpenAIEmbedder by default; call reset_kb_service() in tests to
    inject a different embedder.
    """
    global _service
    if _service is None:
        from src.core.embedding.openai_embedder import OpenAIEmbedder

        path = db_path or Path(os.getenv("KB_DB_PATH", "./data/kb.sqlite"))
        conn = init_db(path)
        paper_store = PaperStore(conn)
        chunk_store = ChunkStore(conn)
        embedder = OpenAIEmbedder()
        strategy = os.getenv("CHUNK_STRATEGY", "char")
        _service = KBService(paper_store, chunk_store, embedder, chunk_strategy=strategy)
    return _service


def reset_kb_service(service: Optional[KBService] = None) -> None:
    """Replace the singleton — intended for testing."""
    global _service
    _service = service
