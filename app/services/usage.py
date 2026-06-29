"""UsageMeter: comptador d'ús de l'LLM (tokens + cost estimat) per mes.

Protecció de factura: l'app consulta `month_cost_eur()` ABANS de cridar Gemini i,
si s'arriba al pressupost mensual, deixa de cridar-lo (retorna un missatge amable).
Backed per SQLite (atòmic i compartit entre workers d'uvicorn). El cost es calcula
sobre la marxa a partir dels tokens i els preus configurats, de manera que canviar
els preus reavalua tot el mes. El comptador es reseteja sol cada mes natural (UTC),
perquè la clau primària és el mes 'YYYY-MM'.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class UsageMeter:
    def __init__(
        self,
        db_path: Path | str,
        price_input_per_million_eur: float,
        price_output_per_million_eur: float,
    ) -> None:
        self._price_in = price_input_per_million_eur
        self._price_out = price_output_per_million_eur
        self._lock = threading.Lock()
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: els endpoints síncrons de FastAPI corren en un
        # threadpool; el Lock serialitza els accessos.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS usage ("
            " month TEXT PRIMARY KEY,"
            " calls INTEGER NOT NULL DEFAULT 0,"
            " input_tokens INTEGER NOT NULL DEFAULT 0,"
            " output_tokens INTEGER NOT NULL DEFAULT 0)"
        )
        self._conn.commit()

    @staticmethod
    def _month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _cost(self, in_tok: int, out_tok: int) -> float:
        return (
            (in_tok / 1_000_000) * self._price_in
            + (out_tok / 1_000_000) * self._price_out
        )

    def _row(self, month: str) -> tuple[int, int, int]:
        cur = self._conn.execute(
            "SELECT calls, input_tokens, output_tokens FROM usage WHERE month = ?",
            (month,),
        )
        r = cur.fetchone()
        return (r[0], r[1], r[2]) if r else (0, 0, 0)

    def record(
        self, input_tokens: int, output_tokens: int, month: str | None = None
    ) -> None:
        """Suma una crida (tokens d'entrada/sortida) al mes indicat (per defecte, l'actual)."""
        m = month or self._month()
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (month, calls, input_tokens, output_tokens)"
                " VALUES (?, 1, ?, ?)"
                " ON CONFLICT(month) DO UPDATE SET"
                " calls = calls + 1,"
                " input_tokens = input_tokens + excluded.input_tokens,"
                " output_tokens = output_tokens + excluded.output_tokens",
                (m, max(0, int(input_tokens)), max(0, int(output_tokens))),
            )
            self._conn.commit()

    def month_cost_eur(self, month: str | None = None) -> float:
        m = month or self._month()
        with self._lock:
            _, in_tok, out_tok = self._row(m)
        return self._cost(in_tok, out_tok)

    def snapshot(
        self, budget_eur: float | None = None, month: str | None = None
    ) -> dict:
        """Estat del mes (per a l'endpoint /api/usage)."""
        m = month or self._month()
        with self._lock:
            calls, in_tok, out_tok = self._row(m)
        cost = self._cost(in_tok, out_tok)
        snap = {
            "month": m,
            "calls": calls,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_eur": round(cost, 4),
        }
        if budget_eur is not None and budget_eur > 0:
            snap["budget_eur"] = budget_eur
            snap["remaining_eur"] = round(max(0.0, budget_eur - cost), 4)
            snap["over_budget"] = cost >= budget_eur
        return snap

    def close(self) -> None:
        with self._lock:
            self._conn.close()
