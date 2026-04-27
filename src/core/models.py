"""Shared Pydantic data models used across all modules."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """Canonical representation of a paper returned by search or stored in KB."""

    internal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str  # "arxiv", "semantic_scholar", "crossref", …
    external_id: str  # arXiv id, DOI, SS paper id, …
    title: str
    abstract: str = ""
    authors: list[str] = []
    year: Optional[int] = None
    venue: str = ""
    url_pdf: str = ""
    citations: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaperChunk(BaseModel):
    """A text chunk from a parsed PDF, optionally carrying an embedding vector."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    paper_id: str
    chunk_index: int
    text: str
    embedding: Optional[list[float]] = None  # None until embedded


class RetrievedChunk(BaseModel):
    """A chunk returned by KB vector search, with its relevance score."""

    paper_id: str
    chunk_index: int
    score: float
    text: str


class IngestResult(BaseModel):
    """Summary returned after a paper is successfully ingested into the KB."""

    paper_id: str
    num_chunks: int
    char_count: int
