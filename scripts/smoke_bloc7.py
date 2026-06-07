"""Smoke test Bloc 7: verifica embedder (cross-lingual) + Gemini LLM.

Ús (al VPS, dins venv):  python scripts/smoke_bloc7.py
Comprova:
  1. L'embedder vectoritza i la similitud CA<->ZH és alta (> 0.5).
  2. Gemini respon (cal GOOGLE_API_KEY al .env).
"""
from __future__ import annotations
import sys
from pathlib import Path

# permet executar com a script: afegeix l'arrel del projecte al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.llm import GeminiLLM


def main() -> None:
    s = get_settings()

    print("1) Carregant embedder (pot trigar el primer cop)...")
    embedder = SentenceTransformersEmbedder(s.embed_model)
    print(f"   dimensio = {embedder.dimension}")

    v_ca = embedder.embed_query("Què deia Plató sobre la justícia a La República?")
    v_zh = embedder.embed_query("柏拉图在《理想国》中关于正义说了什么？")
    dot = sum(a * b for a, b in zip(v_ca, v_zh))
    print(f"   similitud CA<->ZH = {dot:.3f}  (esperat > 0.5)")
    assert dot > 0.5, "Similitud cross-lingual massa baixa!"

    print("2) Provant Gemini LLM...")
    llm = GeminiLLM(s.google_api_key, model=s.gemini_model)
    resp = llm.generate(
        system_prompt="Respon en una sola frase curta en català.",
        user_query="Digues 'hola' i el nom del filòsof Plató.",
        context="(sense context)",
    )
    print(f"   resposta = {resp!r}")

    print("\n[OK] Bloc 7: embedder + LLM funcionen.")


if __name__ == "__main__":
    main()
