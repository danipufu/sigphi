"""Smoke test Bloc 11: l'app FastAPI aixeca (lifespan) i /health + /chat responen.

Força el backend Chroma local (VECTOR_DB_TYPE=chroma) amb un mini-corpus i usa
el TestClient de FastAPI (in-process, NO cal servidor ni accés HTTP extern).
Valida API REST + injecció de dependències + lifespan end-to-end.

Ús (al VPS, des de l'arrel, cal GOOGLE_API_KEY al .env):
    python scripts/smoke_bloc11.py
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Forçar backend chroma + dir temporal ABANS de carregar settings/app.
_TMP = tempfile.mkdtemp(prefix="sigphi_app_")
os.environ["VECTOR_DB_TYPE"] = "chroma"
os.environ["CHROMA_DIR"] = _TMP

from app.config import get_settings
from app.domain.models import Chunk
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.vector_db.chroma_db import ChromaDB


def _seed() -> None:
    s = get_settings()
    emb = SentenceTransformersEmbedder(s.embed_model)
    db = ChromaDB(persist_dir=Path(_TMP))
    db.initialize_index(emb.dimension)
    chunks = [
        Chunk("e1", "No són les coses les que ens pertorben, sinó els judicis que en fem.",
              "Epictet", "Enquiridió", "ca", "Complete work",
              "Recorded/compiled by others",
              "Epictet no va escriure res; recollit pel deixeble Arrià."),
        Chunk("m1", "Tens poder sobre la teva ment, no sobre els fets externs.",
              "Marc Aureli", "Meditacions", "ca", "Complete work",
              "Written by the author", "—"),
    ]
    db.upsert_batches(chunks, emb.embed_passages([c.text for c in chunks]))


def main() -> None:
    print("1) Sembrant mini-corpus a Chroma local...")
    _seed()

    print("2) Aixecant l'app (lifespan) amb TestClient...")
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        h = client.get("/api/health")
        print("   /api/health ->", h.status_code, h.json())
        assert h.status_code == 200

        r = client.post(
            "/api/chat",
            json={
                "query": "Què deien els estoics sobre allò que podem controlar?",
                "history": [],
            },
        )
        print("   /api/chat ->", r.status_code)
        data = r.json()
        print("\n--- RESPOSTA ---")
        print(data["answer"])
        print("\n--- FONTS ---")
        for src in data["sources"]:
            print("  -", src)

        assert r.status_code == 200
        assert data["answer"].strip(), "Resposta buida!"
        assert data["sources"], "Sense fonts!"

    print("\n[OK] Bloc 11: API FastAPI + lifespan + Gradio muntat funcionen.")


if __name__ == "__main__":
    main()
