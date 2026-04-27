"""SQLite connection management and schema initialisation."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(os.getenv("KB_DB_PATH", "./data/kb.sqlite"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title       TEXT NOT NULL,
    abstract    TEXT,
    authors     TEXT,        -- JSON array
    year        INTEGER,
    venue       TEXT,
    url_pdf     TEXT,
    citations   INTEGER,
    created_at  TEXT NOT NULL,
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id          TEXT PRIMARY KEY,
    paper_id    TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   BLOB         -- NULL until embedded; serialised as float32 bytes
);

CREATE TABLE IF NOT EXISTS paper_tags (
    paper_id    TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (paper_id, tag)
);

CREATE TABLE IF NOT EXISTS kb_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
"""


def get_db(path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    conn = get_db(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn
