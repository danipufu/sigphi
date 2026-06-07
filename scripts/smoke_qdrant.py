"""Smoke test del backend Qdrant: round-trip + author_filter + hidratació.

Usa Qdrant en mode :memory: (sense servidor) per validar la LÒGICA del backend
(upsert -> query -> filtre -> hidratació de text des del ChunkStore). La
quantització/on_disk només s'activen contra un Qdrant real (servidor al VPS).

Ús (al VPS, des de l'arrel):  python scripts/smoke_qdrant.py
"""
from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.domain.models import Chunk
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.vector_db.qdrant_db import QdrantDB


def main() -> None:
    s = get_settings()
    print("1) Carregant embedder...")
    emb = SentenceTransformersEmbedder(s.embed_model)

    tmp = Path(tempfile.mkdtemp(prefix="sigphi_qdrant_"))
    try:
        cs = ChunkStore(tmp / "chunks.sqlite")
        db = QdrantDB(
            url=":memory:", collection="sigphi_test",
            chunk_store=cs, use_quantization=False,
        )
        db.initialize_index(emb.dimension)

        chunks = [
            Chunk("c1", "La justícia és l'harmonia de l'ànima i de la ciutat.",
                  "Plató", "La República", "ca",
                  "Complete work", "Written by the author", "—"),
            Chunk("c2", "Comença el dia recordant que tractaràs amb gent difícil.",
                  "Marc Aureli", "Meditacions", "ca",
                  "Complete work", "Recorded/compiled by others", "—"),
            Chunk("c3", "Déu ha mort i nosaltres l'hem matat.",
                  "Nietzsche", "La gaia ciència", "ca",
                  "Complete work", "Written by the author", "—"),
        ]
        db.upsert_batches(chunks, emb.embed_passages([c.text for c in chunks]))

        print("2) Query SENSE filtre: 'Què és la justícia per a Plató?'")
        qv = emb.embed_query("Què és la justícia per a Plató?")
        res = db.query_similarity(qv, top_k=3)
        for r in res:
            print(f"   {r.score:.3f}  {r.chunk.author} — {r.chunk.work}")
        assert res[0].chunk.author == "Plató", "El top-1 hauria de ser Plató"
        assert res[0].chunk.text, "El text no s'ha hidratat des del ChunkStore!"

        print("3) Query AMB author_filter=['Nietzsche']")
        res2 = db.query_similarity(qv, top_k=3, author_filter=["Nietzsche"])
        for r in res2:
            print(f"   {r.score:.3f}  {r.chunk.author} — {r.chunk.work}")
        assert res2 and all(r.chunk.author == "Nietzsche" for r in res2), \
            "El filtre d'autor no funciona!"

        print("\n[OK] Backend Qdrant: round-trip + author_filter + hidratació funcionen.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
