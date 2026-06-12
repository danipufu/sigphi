"""ChunkStore: persistència local del text complet dels fragments.

Per què existeix:
    Pinecone Starter (free tier) limita la metadata a ~40 KB per registre i té
    storage limitat. Si guardéssim el text complet del chunk com a metadata,
    sobrepassaríem la quota. Aquí guardem (text + metadades), i Pinecone només
    guarda (chunk_id, vector, metadata mínima per filtrar per autor).

Patró:
    - Open atomic: la conn es comparteix entre handlers async (check_same_thread=False)
    - WAL mode: permet lectors concurrents mentre s'escriu (ingesta + queries simultànies)
    - INSERT OR REPLACE: la ingesta és resumible (repetir un chunk no duplica)
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Sequence

from app.domain.models import Chunk


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    author       TEXT NOT NULL,
    work         TEXT NOT NULL,
    language     TEXT NOT NULL,
    completeness TEXT NOT NULL,
    authorship   TEXT NOT NULL,
    note         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_author ON chunks(author);
"""


class ChunkStore:
    """SQLite-backed store for chunk text and metadata."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
        )
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.commit()

    def upsert_many(self, chunks: Sequence[Chunk]) -> int:
        """Inserts or replaces N chunks atomically. Retorna count upserted."""
        if not chunks:
            return 0
        rows = [
            (c.chunk_id, c.text, c.author, c.work, c.language,
             c.completeness, c.authorship, c.note)
            for c in chunks
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks "
            "(chunk_id, text, author, work, language, completeness, authorship, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return len(rows)

    def get_by_ids(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """Retorna chunks indexats per chunk_id (només els trobats)."""
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" * len(chunk_ids))
        cur = self._conn.execute(
            f"SELECT chunk_id, text, author, work, language, "
            f"completeness, authorship, note FROM chunks "
            f"WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        )
        return {
            row[0]: Chunk(
                chunk_id=row[0], text=row[1], author=row[2], work=row[3],
                language=row[4], completeness=row[5], authorship=row[6],
                note=row[7],
            )
            for row in cur.fetchall()
        }

    def count(self) -> int:
        """Total chunks indexats."""
        return self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def catalog(self) -> list[dict]:
        """Autors amb les seves obres, llegits de la BD real (per a /api/catalog)."""
        cur = self._conn.execute(
            "SELECT author, work FROM chunks GROUP BY author, work ORDER BY author, work"
        )
        by_author: dict[str, list[str]] = {}
        for author, work in cur.fetchall():
            by_author.setdefault(author, []).append(work)
        return [{"author": a, "works": w} for a, w in by_author.items()]

    def sample(self, author: str, work: str | None = None, n: int = 1) -> list[str]:
        """Primers n fragments d'una obra (o autor) per inspeccionar el text REAL
        (detectar portades, pròlegs del traductor, editorial, brossa d'OCR...).
        Ordre per chunk_id: el '#0' (inici del llibre) surt primer."""
        if work:
            cur = self._conn.execute(
                "SELECT text FROM chunks WHERE author=? AND work=? ORDER BY chunk_id LIMIT ?",
                (author, work, n),
            )
        else:
            cur = self._conn.execute(
                "SELECT text FROM chunks WHERE author=? ORDER BY chunk_id LIMIT ?",
                (author, n),
            )
        return [r[0] for r in cur.fetchall()]

    # --- neteja (eliminar obres/autors mal classificats) ---
    def find_works(self, author: str, contains: str) -> list[str]:
        """Obres d'un autor el títol de les quals conté 'contains' (per trobar
        descàrregues equivocades, robust a títols truncats)."""
        cur = self._conn.execute(
            "SELECT DISTINCT work FROM chunks WHERE author=? AND work LIKE ?",
            (author, f"%{contains}%"),
        )
        return [r[0] for r in cur.fetchall()]

    def chunk_ids_of(self, author: str, work: str | None = None) -> list[str]:
        if work:
            cur = self._conn.execute(
                "SELECT chunk_id FROM chunks WHERE author=? AND work=?", (author, work)
            )
        else:
            cur = self._conn.execute(
                "SELECT chunk_id FROM chunks WHERE author=?", (author,)
            )
        return [r[0] for r in cur.fetchall()]

    def delete_ids(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        self._conn.executemany(
            "DELETE FROM chunks WHERE chunk_id=?", [(c,) for c in chunk_ids]
        )
        self._conn.commit()
        return len(chunk_ids)

    def close(self) -> None:
        self._conn.close()
