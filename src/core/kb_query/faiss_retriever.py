"""FAISS-based vector retriever (V2).

Uses an exact inner-product index (IndexFlatIP) over L2-normalised vectors,
which is equivalent to cosine similarity without an approximate-NN approximation.

The index is rebuilt lazily whenever the chunk count in the DB has changed since
the last build — cheap for read-heavy workloads, avoids stale results after ingest.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from src.core.models import RetrievedChunk
from src.core.embedding.base import BaseEmbedder
from src.core.kb_store.chunk_store import ChunkStore

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FAISS_AVAILABLE = False


class FaissRetriever:
    """Drop-in replacement for KBRetriever backed by FAISS IndexFlatIP."""

    def __init__(self, chunk_store: ChunkStore, embedder: BaseEmbedder) -> None:
        if not _FAISS_AVAILABLE:  # pragma: no cover
            raise ImportError("faiss-cpu is required for FaissRetriever. Run: pip install faiss-cpu")
        self._chunks = chunk_store
        self._embedder = embedder

        # Index state
        self._index: Optional[faiss.IndexFlatIP] = None
        self._meta: list[dict] = []   # parallel list: index position → chunk metadata
        self._indexed_count: int = 0  # chunk count at last build

    # ------------------------------------------------------------------
    # Public API (same signature as KBRetriever.search)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        top_k: int = 5,
        paper_ids: Optional[list[str]] = None,
    ) -> list[RetrievedChunk]:
        self._maybe_rebuild()
        if self._index is None or self._index.ntotal == 0:
            return []

        query_vec = await self._embedder.embed_one(query)
        q = _to_matrix([query_vec])          # shape (1, dim)

        # When paper_ids filter is active we restrict the search post-hoc.
        # FAISS doesn't natively support per-query ID filters, so we over-fetch
        # and then trim; this is fine for V2 scale.
        k = min(self._index.ntotal, top_k * 10 if paper_ids else top_k)
        scores, indices = self._index.search(q, k)

        results: list[RetrievedChunk] = []
        pid_set = set(paper_ids) if paper_ids else None
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            meta = self._meta[idx]
            if pid_set and meta["paper_id"] not in pid_set:
                continue
            results.append(
                RetrievedChunk(
                    paper_id=meta["paper_id"],
                    chunk_index=meta["chunk_index"],
                    score=round(float(score), 4),
                    text=meta["text"],
                )
            )
            if len(results) >= top_k:
                break
        return results

    def rebuild_index(self) -> None:
        """Force a full index rebuild from the current DB state."""
        self._build()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _maybe_rebuild(self) -> None:
        current_count = len(self._chunks.get_all_with_embeddings())
        if current_count != self._indexed_count:
            self._build()

    def _build(self) -> None:
        all_chunks = self._chunks.get_all_with_embeddings()
        if not all_chunks:
            self._index = None
            self._meta = []
            self._indexed_count = 0
            return

        vecs = np.array([c.embedding for c in all_chunks], dtype="float32")
        # L2-normalise so IndexFlatIP == cosine similarity
        faiss.normalize_L2(vecs)

        dim = vecs.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vecs)

        self._index = index
        self._meta = [
            {"paper_id": c.paper_id, "chunk_index": c.chunk_index, "text": c.text}
            for c in all_chunks
        ]
        self._indexed_count = len(all_chunks)


def _to_matrix(vecs: list[list[float]]) -> np.ndarray:
    m = np.array(vecs, dtype="float32")
    faiss.normalize_L2(m)
    return m
