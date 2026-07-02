"""TelemetryStore: registre lleuger (SQLite) de torns i feedback.

Per què existeix: sense això no sabem QUÈ pregunta la gent real ni ON falla
el sistema (taxa de NO_SOURCES, score mitjà de retrieval, llatència) -- decidir
on invertir després (reranker? cerca híbrida? embedder millor?) seria pura
intuïció. Backed per SQLite, mateix patró que UsageMeter (WAL, lock,
check_same_thread=False: els endpoints síncrons de FastAPI corren en threadpool).

Anonimitzat per disseny: NO es desa cap IP ni identificador d'usuari (encara no
hi ha comptes). Es desa el text de la consulta (per entendre patrons d'ús real)
i metadades tècniques del torn -- res més.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Tope defensiu de longitud de consulta desada (una consulta anòmalament llarga
# no ha d'inflar la BD ni trencar res).
_MAX_QUERY_LEN = 500


class TelemetryStore:
    def __init__(self, db_path: Path | str) -> None:
        self._lock = threading.Lock()
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS turns ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL,"
            " query TEXT NOT NULL,"
            " authors TEXT NOT NULL DEFAULT '',"
            " n_retrieved INTEGER NOT NULL DEFAULT 0,"
            " top_score REAL,"
            " sources_count INTEGER NOT NULL DEFAULT 0,"
            " no_sources INTEGER NOT NULL DEFAULT 0,"
            " suggestions_count INTEGER NOT NULL DEFAULT 0,"
            " unverified_count INTEGER NOT NULL DEFAULT 0,"
            " latency_ms INTEGER"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);"
            "CREATE TABLE IF NOT EXISTS feedback ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts TEXT NOT NULL,"
            " query TEXT NOT NULL,"
            " vote INTEGER NOT NULL"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts);"
        )
        self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_turn(
        self,
        query: str,
        *,
        authors: list[str] | None = None,
        n_retrieved: int = 0,
        top_score: float | None = None,
        sources_count: int = 0,
        no_sources: bool = False,
        suggestions_count: int = 0,
        unverified_count: int = 0,
        latency_ms: int | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO turns (ts, query, authors, n_retrieved, top_score,"
                " sources_count, no_sources, suggestions_count, unverified_count, latency_ms)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    self._now(),
                    (query or "")[:_MAX_QUERY_LEN],
                    ",".join(authors or []),
                    n_retrieved,
                    top_score,
                    sources_count,
                    int(no_sources),
                    suggestions_count,
                    unverified_count,
                    latency_ms,
                ),
            )
            self._conn.commit()

    def record_feedback(self, query: str, vote: int) -> None:
        """vote: >0 -> polze amunt (desat com +1), <=0 -> polze avall (desat com -1)."""
        v = 1 if vote > 0 else -1
        with self._lock:
            self._conn.execute(
                "INSERT INTO feedback (ts, query, vote) VALUES (?, ?, ?)",
                (self._now(), (query or "")[:_MAX_QUERY_LEN], v),
            )
            self._conn.commit()

    def stats(self, days: int = 30) -> dict:
        """Resum agregat dels últims `days` dies (per a /api/stats)."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            n, no_src, avg_score, avg_lat, avg_src, unverified_sum = self._conn.execute(
                "SELECT COUNT(*), SUM(no_sources), AVG(top_score), AVG(latency_ms),"
                " AVG(sources_count), SUM(unverified_count) FROM turns WHERE ts >= ?",
                (since,),
            ).fetchone()
            votes = dict(
                self._conn.execute(
                    "SELECT vote, COUNT(*) FROM feedback WHERE ts >= ? GROUP BY vote",
                    (since,),
                ).fetchall()
            )
            top_queries = [
                {"query": q, "count": c}
                for q, c in self._conn.execute(
                    "SELECT query, COUNT(*) c FROM turns WHERE ts >= ?"
                    " GROUP BY query ORDER BY c DESC LIMIT 10",
                    (since,),
                ).fetchall()
            ]
        n = n or 0
        return {
            "days": days,
            "turns": n,
            "no_sources_rate": round((no_src or 0) / n, 3) if n else None,
            "avg_top_score": round(avg_score, 3) if avg_score is not None else None,
            "avg_latency_ms": round(avg_lat) if avg_lat is not None else None,
            "avg_sources_per_turn": round(avg_src, 2) if avg_src is not None else None,
            "unverified_citations_total": unverified_sum or 0,
            "feedback_up": votes.get(1, 0),
            "feedback_down": votes.get(-1, 0),
            "top_queries": top_queries,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
