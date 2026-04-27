"""Download a PDF from a URL and cache it locally."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_DEFAULT_CACHE = Path(os.getenv("PDF_CACHE_DIR", "./data/pdf_cache"))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
async def download_pdf(url: str, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    """Download *url* to *cache_dir* (keyed by URL hash) and return the local path."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    dest = cache_dir / f"{url_hash}.pdf"
    if dest.exists():
        return dest
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest
