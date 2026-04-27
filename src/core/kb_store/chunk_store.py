"""CRUD operations for the `paper_chunks` table, including embedding storage."""

from __future__ import annotations

import sqlite3
import struct

from src.core.models import PaperChunk


class ChunkStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_chunks(self, chunks: list[PaperChunk]) -> None:
        rows = [
            (
                c.id,
                c.paper_id,
                c.chunk_index,
                c.text,
                _encode_embedding(c.embedding) if c.embedding else None,
            )
            for c in chunks
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO paper_chunks (id, paper_id, chunk_index, text, embedding) VALUES (?,?,?,?,?)",
            rows,
        )
        self._conn.commit()

    def get_chunks_by_paper(self, paper_id: str) -> list[PaperChunk]:
        rows = self._conn.execute(
            "SELECT * FROM paper_chunks WHERE paper_id=? ORDER BY chunk_index",
            (paper_id,),
        ).fetchall()
        return [_row_to_chunk(r) for r in rows]

    def get_all_with_embeddings(self) -> list[PaperChunk]:
        rows = self._conn.execute(
            "SELECT * FROM paper_chunks WHERE embedding IS NOT NULL"
        ).fetchall()
        return [_row_to_chunk(r) for r in rows]

    def update_embedding(self, chunk_id: str, embedding: list[float]) -> None:
        self._conn.execute(
            "UPDATE paper_chunks SET embedding=? WHERE id=?",
            (_encode_embedding(embedding), chunk_id),
        )
        self._conn.commit()

    def count_by_paper(self, paper_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM paper_chunks WHERE paper_id=?", (paper_id,)
        ).fetchone()
        return row[0]


def _encode_embedding(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _decode_embedding(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _row_to_chunk(row: sqlite3.Row) -> PaperChunk:
    d = dict(row)
    blob = d.pop("embedding", None)
    d["embedding"] = _decode_embedding(blob) if blob else None
    return PaperChunk(**d)
