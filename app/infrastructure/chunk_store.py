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

Cerca lèxica (BM25, cerca híbrida):
    chunks_fts és una taula virtual FTS5 (BM25 natiu de SQLite) que espilla
    chunk_id+text, sincronitzada a mà (no external-content, per evitar la
    complexitat de triggers amb INSERT OR REPLACE que canvia el rowid). Troba
    coincidències lèxiques exactes (noms propis, títols concrets) que la cerca
    semàntica pot perdre. Es fa un backfill automàtic si la BD ja tenia chunks
    d'abans que existís aquesta taula (vegeu _backfill_fts_if_needed).
"""
from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from typing import Sequence

from app.domain.models import Chunk, RetrievedChunk


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

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, text);
"""

# Termes de cerca FTS5: paraules soles, entre cometes (evita que caràcters com
# ( ) " - * : , que l'usuari pugui escriure es confonguin amb operadors FTS5).
_FTS_TERM_RE = re.compile(r"\w+", re.UNICODE)
_FTS_MAX_TERMS = 12


def _fts5_query(text: str) -> str:
    """Consulta en llenguatge natural -> consulta FTS5 seguríssima: paraules amb
    OR (recall ampli; el ranking bm25() ja premia qui en casa més)."""
    terms = [t for t in _FTS_TERM_RE.findall(text or "") if len(t) >= 2]
    if not terms:
        return ""
    return " OR ".join(f'"{t}"' for t in terms[:_FTS_MAX_TERMS])


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
        self._backfill_fts_if_needed()

    def _backfill_fts_if_needed(self) -> None:
        """Si chunks_fts és nova/buida però ja hi ha chunks (BD d'abans que
        existís aquesta taula), la indexa d'un cop. Auto-curatiu: no cal cap
        script de migració separat."""
        fts_count = self._conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
        if fts_count > 0:
            return
        total = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if total == 0:
            return
        self._conn.execute(
            "INSERT INTO chunks_fts (chunk_id, text) SELECT chunk_id, text FROM chunks"
        )
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
        # chunks_fts no té restricció d'unicitat pròpia (taula virtual FTS5):
        # esborra-i-insereix per cobrir tant l'alta nova com el REPLACE.
        ids = [(c.chunk_id,) for c in chunks]
        self._conn.executemany("DELETE FROM chunks_fts WHERE chunk_id = ?", ids)
        self._conn.executemany(
            "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
            [(c.chunk_id, c.text) for c in chunks],
        )
        self._conn.commit()
        return len(rows)

    def search_bm25(
        self,
        query: str,
        top_k: int,
        author_filter: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """Cerca lèxica (BM25 natiu de FTS5): troba coincidències de paraula
        exactes que la cerca semàntica pot perdre (noms propis, títols
        concrets, termes tècnics poc freqüents). bm25() de FTS5 retorna
        puntuacions NEGATIVES on més negatiu = més rellevant (ORDER BY ASC)."""
        fts_query = _fts5_query(query)
        if not fts_query:
            return []
        sql = (
            "SELECT c.chunk_id, c.text, c.author, c.work, c.language, c.completeness,"
            " c.authorship, c.note, bm25(chunks_fts) AS rank"
            " FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id"
            " WHERE chunks_fts MATCH ?"
        )
        params: list = [fts_query]
        if author_filter:
            placeholders = ",".join("?" * len(author_filter))
            sql += f" AND c.author IN ({placeholders})"
            params.extend(author_filter)
        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []  # consulta FTS5 mal formada (rar); mai trenca el retrieval
        out: list[RetrievedChunk] = []
        for row in rows:
            chunk = Chunk(
                chunk_id=row[0], text=row[1], author=row[2], work=row[3],
                language=row[4], completeness=row[5], authorship=row[6], note=row[7],
            )
            # Normalitza el rank (negatiu, sense tope) a un pseudo-score [0,1)
            # només per coherència visual amb el score de l'embedder; la fusió
            # híbrida (RRF) fa servir la POSICIÓ, no aquest valor.
            score = 1.0 / (1.0 + max(0.0, -row[8]))
            out.append(RetrievedChunk(chunk=chunk, score=score))
        return out

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

    def chunk_ids_of_file(self, filename: str) -> list[str]:
        """Chunks provinents d'un FITXER d'origen concret. El chunk_id és
        `{nom_fitxer}#{n}` (vegeu ingest.py), així que es pot discriminar pel fitxer
        encara que dues entrades comparteixin autor+títol (p.ex. difereixin només en
        majúscules) i no es puguin separar amb find_works (LIKE, insensible a majúsc.)."""
        cur = self._conn.execute(
            "SELECT chunk_id FROM chunks WHERE chunk_id LIKE ? ESCAPE '\\'",
            (filename.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "#%",),
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
        rows = [(c,) for c in chunk_ids]
        self._conn.executemany("DELETE FROM chunks WHERE chunk_id=?", rows)
        self._conn.executemany("DELETE FROM chunks_fts WHERE chunk_id=?", rows)
        self._conn.commit()
        return len(chunk_ids)

    def close(self) -> None:
        self._conn.close()
