"""Smoke test Bloc 8: round-trip del VectorDB + author_filter.

Usa ChromaDB LOCAL (no cal compte Pinecone) per validar la interfície:
upsert -> query -> hidratació de text -> filtre per autor.
La implementació de Pinecone compleix EXACTAMENT el mateix contracte.

Ús (al VPS, dins venv):  python scripts/smoke_bloc8.py
"""
from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.domain.models import Chunk
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.vector_db.chroma_db import ChromaDB


def main() -> None:
    s = get_settings()

    print("1) Carregant embedder...")
    emb = SentenceTransformersEmbedder(s.embed_model)

    tmp = Path(tempfile.mkdtemp(prefix="sigphi_chroma_"))
    try:
        db = ChromaDB(persist_dir=tmp)
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
        vecs = emb.embed_passages([c.text for c in chunks])
        n = db.upsert_batches(chunks, vecs)
        print(f"   upsert: {n} chunks")

        print("2) Query SENSE filtre: 'Què és la justícia per a Plató?'")
        qv = emb.embed_query("Què és la justícia per a Plató?")
        res = db.query_similarity(qv, top_k=3)
        for r in res:
            print(f"   {r.score:.3f}  {r.chunk.author} — {r.chunk.work}")
        assert res[0].chunk.author == "Plató", "El top-1 hauria de ser Plató"
        assert res[0].chunk.text, "El text no s'ha hidratat!"

        print("3) Query AMB author_filter=['Nietzsche']")
        res2 = db.query_similarity(qv, top_k=3, author_filter=["Nietzsche"])
        for r in res2:
            print(f"   {r.score:.3f}  {r.chunk.author} — {r.chunk.work}")
        assert res2, "El filtre no hauria de retornar buit"
        assert all(r.chunk.author == "Nietzsche" for r in res2), \
            "El filtre d'autor deixa passar altres autors!"

        print("\n[OK] Bloc 8: VectorDB round-trip + author_filter funcionen.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
