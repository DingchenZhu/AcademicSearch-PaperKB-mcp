"""Deterministic fake embedder for unit and integration tests.

Returns a fixed-dimension vector derived from the input text so that
semantically distinct strings get different (but reproducible) vectors,
letting tests verify retrieval ordering without calling any real API.
"""

from __future__ import annotations

import hashlib
import math

from .base import BaseEmbedder

_DIM = 8  # small dimension keeps tests fast


class FakeEmbedder(BaseEmbedder):
    """Hash-based embedder that is fast, deterministic, and offline."""

    def __init__(self, dim: int = _DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        raw = [
            (digest[i % len(digest)] / 255.0) * 2 - 1
            for i in range(self._dim)
        ]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]
