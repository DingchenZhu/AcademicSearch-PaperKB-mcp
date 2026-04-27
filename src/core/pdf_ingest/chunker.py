"""Text chunking strategies for ingested PDF content.

Two strategies are provided and selectable via the CHUNK_STRATEGY env var:
  - "char"      (default): fixed-size character window with overlap
  - "paragraph": paragraph-boundary-aware grouping with paragraph-level overlap

Use make_chunker() to get the right function based on the environment.
"""

from __future__ import annotations

import os
import re


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> list[str]:
    """Fixed-size character chunking with overlap.

    Original V0/V1 strategy — kept for backwards compatibility and as the
    safe fallback when the text has no paragraph structure.
    """
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def paragraph_chunk(
    text: str,
    target_size: int = 1000,
    overlap_paragraphs: int = 1,
    min_paragraph_len: int = 20,
) -> list[str]:
    """Paragraph-boundary-aware chunking (V3).

    Splits text on blank lines, groups paragraphs until the target character
    budget is reached, then starts a new chunk.  The last *overlap_paragraphs*
    paragraphs of the previous chunk are prepended to the next one so that
    cross-boundary context is preserved.

    Falls back to chunk_text() when no paragraph structure is detected
    (single long paragraph without any blank lines).
    """
    if not text.strip():
        return []

    raw = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in raw if len(p.strip()) >= min_paragraph_len]

    if not paragraphs:
        return []

    # If there is only one very long paragraph, fall back to char chunking
    if len(paragraphs) == 1:
        return chunk_text(paragraphs[0], chunk_size=target_size, overlap=target_size // 10)

    chunks: list[str] = []
    current: list[str] = []
    current_len: int = 0

    for para in paragraphs:
        if current_len + len(para) > target_size and current:
            chunks.append("\n\n".join(current))
            # Overlap: carry the last N paragraphs into the next chunk
            overlap = current[-overlap_paragraphs:] if overlap_paragraphs > 0 else []
            current = overlap[:]
            current_len = sum(len(p) for p in current)
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def make_chunker(strategy: str | None = None):
    """Return the chunking function selected by *strategy* or CHUNK_STRATEGY env var.

    Returned callable signature: ``fn(text: str) -> list[str]``
    """
    chosen = (strategy or os.getenv("CHUNK_STRATEGY", "char")).lower()
    if chosen == "paragraph":
        return paragraph_chunk
    return chunk_text
