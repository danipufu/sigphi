"""Smoke test Bloc 9: RAG end-to-end (Chroma local + Gemini) amb caveat d'autoria.

Verifica el pipeline complet: retrieve -> context amb CAVEAT -> LLM -> fonts.
Munta un mini-corpus (Epictet recollit per Arrià + Marc Aureli) i comprova que
la resposta surt amb fonts i que apareix l'avís ⚠ d'autoria no directa.

Ús (al VPS, des de l'arrel del projecte, cal GOOGLE_API_KEY al .env):
    python scripts/smoke_bloc9.py
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
from app.infrastructure.llm import GeminiLLM
from app.infrastructure.vector_db.chroma_db import ChromaDB
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService


def main() -> None:
    s = get_settings()

    print("1) Carregant embedder + LLM...")
    emb = SentenceTransformersEmbedder(s.embed_model)
    llm = GeminiLLM(s.google_api_key, model=s.gemini_model)

    tmp = Path(tempfile.mkdtemp(prefix="sigphi_chroma_"))
    try:
        db = ChromaDB(persist_dir=tmp)
        db.initialize_index(emb.dimension)
        chunks = [
            Chunk("e1",
                  "No són les coses les que ens pertorben, sinó els judicis que en fem.",
                  "Epictet", "Enquiridió", "ca", "Complete work",
                  "Recorded/compiled by others",
                  "Epictet no va escriure res; els ensenyaments els va recollir el deixeble Arrià."),
            Chunk("m1",
                  "Tens poder sobre la teva ment, no sobre els fets externs; adona-te'n i trobaràs força.",
                  "Marc Aureli", "Meditacions", "ca", "Complete work",
                  "Written by the author", "—"),
        ]
        db.upsert_batches(chunks, emb.embed_passages([c.text for c in chunks]))

        retrieval = RetrievalService(emb, db, s.aliases_path, top_k=s.top_k)
        chat = ChatService(llm, retrieval)

        q = "Què deien els estoics sobre allò que podem controlar?"
        print(f"2) Pregunta: {q}\n")
        res = chat.answer(q)

        print("--- RESPOSTA ---")
        print(res.answer)
        print("\n--- FONTS ---")
        for src in res.sources:
            print("  -", src)

        assert res.answer.strip(), "Resposta buida!"
        assert res.sources, "Sense fonts!"
        assert any("⚠" in src for src in res.sources), \
            "Hauria d'aparèixer un avís ⚠ per Epictet (recollit per Arrià)"

        print("\n[OK] Bloc 9: RAG end-to-end + caveats funcionen.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
