"""Factory for selecting the right retriever backend at runtime."""

from __future__ import annotations

import os

from src.core.embedding.base import BaseEmbedder
from src.core.kb_store.chunk_store import ChunkStore
from .retriever import KBRetriever

_BACKEND_ENV = "KB_RETRIEVER_BACKEND"  # "linear" (default) or "faiss"


def make_retriever(chunk_store: ChunkStore, embedder: BaseEmbedder):
    """Return a KBRetriever or FaissRetriever based on KB_RETRIEVER_BACKEND env var."""
    backend = os.getenv(_BACKEND_ENV, "linear").lower()
    if backend == "faiss":
        from .faiss_retriever import FaissRetriever
        return FaissRetriever(chunk_store, embedder)
    return KBRetriever(chunk_store, embedder)
