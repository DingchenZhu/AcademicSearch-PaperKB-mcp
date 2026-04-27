"""Vector retrieval over paper chunks (V0: linear cosine scan)."""

from __future__ import annotations

import math
from typing import Optional

from src.core.models import RetrievedChunk, PaperChunk
from src.core.embedding.base import BaseEmbedder
from src.core.kb_store.chunk_store import ChunkStore


class KBRetriever:
    def __init__(self, chunk_store: ChunkStore, embedder: BaseEmbedder) -> None:
        self._chunks = chunk_store
        self._embedder = embedder

    async def search(
        self,
        query: str,
        top_k: int = 5,
        paper_ids: Optional[list[str]] = None,
    ) -> list[RetrievedChunk]:
        """Return the top-k most relevant chunks for *query*.

        If *paper_ids* is provided, only chunks from those papers are considered.
        """
        query_vec = await self._embedder.embed_one(query)
        candidates: list[PaperChunk] = self._chunks.get_all_with_embeddings()
        if paper_ids is not None:
            pid_set = set(paper_ids)
            candidates = [c for c in candidates if c.paper_id in pid_set]

        scored: list[tuple[float, PaperChunk]] = []
        for chunk in candidates:
            if chunk.embedding:
                score = _cosine(query_vec, chunk.embedding)
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedChunk(
                paper_id=c.paper_id,
                chunk_index=c.chunk_index,
                score=round(s, 4),
                text=c.text,
            )
            for s, c in scored[:top_k]
        ]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
