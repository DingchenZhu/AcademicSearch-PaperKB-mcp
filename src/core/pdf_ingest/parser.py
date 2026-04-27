"""Extract plain text from a PDF file using PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def parse_pdf(path: Path) -> str:
    """Return the full extracted text of *path* as a single string."""
    doc = fitz.open(str(path))
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return "\n".join(pages)
