"""CRUD operations for the `papers` and `paper_tags` tables."""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from src.core.models import Paper


class PaperStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, paper: Paper) -> str:
        """Insert or ignore a paper; return its internal_id."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO papers
              (id, source, external_id, title, abstract, authors, year, venue, url_pdf, citations, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper.internal_id,
                paper.source,
                paper.external_id,
                paper.title,
                paper.abstract,
                json.dumps(paper.authors),
                paper.year,
                paper.venue,
                paper.url_pdf,
                paper.citations,
                paper.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id FROM papers WHERE source=? AND external_id=?",
            (paper.source, paper.external_id),
        ).fetchone()
        return row["id"]

    def get(self, paper_id: str) -> Optional[Paper]:
        row = self._conn.execute(
            "SELECT * FROM papers WHERE id=?", (paper_id,)
        ).fetchone()
        return _row_to_paper(row) if row else None

    def list(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
    ) -> list[Paper]:
        sql = "SELECT DISTINCT p.* FROM papers p"
        params: list = []
        joins, wheres = [], []
        if tag:
            joins.append("JOIN paper_tags pt ON pt.paper_id = p.id")
            wheres.append("pt.tag = ?")
            params.append(tag)
        if query:
            wheres.append("(p.title LIKE ? OR p.abstract LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        if year_from:
            wheres.append("p.year >= ?")
            params.append(year_from)
        if year_to:
            wheres.append("p.year <= ?")
            params.append(year_to)
        if joins:
            sql += " " + " ".join(joins)
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY p.created_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_paper(r) for r in rows]

    def add_tags(self, paper_id: str, tags: list[str]) -> None:
        self._conn.executemany(
            "INSERT OR IGNORE INTO paper_tags (paper_id, tag) VALUES (?, ?)",
            [(paper_id, t) for t in tags],
        )
        self._conn.commit()


def _row_to_paper(row: sqlite3.Row) -> Paper:
    d = dict(row)
    d["authors"] = json.loads(d.get("authors") or "[]")
    d["internal_id"] = d.pop("id")
    return Paper(**d)
