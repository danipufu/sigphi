"""Configuration management amb Pydantic Settings.

Llegeix de variables d'entorn i/o del fitxer .env.
Valida tipus a l'engegada: si falta un valor obligatori, peta net amb missatge clar.
Patró: get_settings() amb lru_cache (es carrega un sol cop, es comparteix).
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuració de l'aplicació SigPhi.

    Usar via get_settings() (cached). Els camps amb default = "" permeten
    importar la config sense petar; la validació real es fa quan el component
    intenta usar la clau (ex: GeminiLLM si google_api_key és buida).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === LLM ===
    google_api_key: str = ""
    # FREE TIER = només ~20 req/DIA per model (esgotat de seguida). La quota és PER
    # MODEL, així que canviar de model dóna un dipòsit fresc avui. flash-lite és ACTUAL
    # (gemini-2.0-flash està obsolet des de juny-2026). Per a ús real cal activar
    # FACTURACIÓ (paid tier, baratíssim) -> sense topall diari. Sobreescrivible amb GEMINI_MODEL al .env.
    gemini_model: str = "gemini-2.5-flash-lite"
    # Clau secreta per a l'endpoint GET /api/ask (verificació externa). Buit = desactivat.
    ask_api_key: str = ""

    # === Vector DB (selector dinàmic) ===
    vector_db_type: Literal["pinecone", "chroma", "qdrant"] = "pinecone"

    # === Pinecone (només si vector_db_type == "pinecone") ===
    pinecone_api_key: str = ""
    pinecone_index_name: str = "sigphi-corpus"
    pinecone_cloud: Literal["aws", "gcp", "azure"] = "aws"
    pinecone_region: str = "us-east-1"

    # === ChromaDB local (futur, només si vector_db_type == "chroma") ===
    chroma_dir: Path = Path("./chroma_db")

    # === Qdrant self-hosted (corpus complet al VPS, només si type == "qdrant") ===
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sigphi"
    # quantització escalar INT8 (4x) + vectors on_disk -> 575k cap en poca RAM
    qdrant_use_quantization: bool = True

    # === Embedder local ===
    embed_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # === Chunk store (SQLite: text complet dels fragments) ===
    chunk_store_path: Path = Path("./data/chunks.sqlite")

    # === Aliases multilingües (12 idiomes + original) ===
    aliases_path: Path = Path("./app/data/authors_aliases.json")

    # === Retrieval ===
    top_k: int = 15

    # === Ingest ===
    ingest_batch_size: int = 100

    # === Rate limit (FastAPI/slowapi) ===
    rate_limit: str = "10/minute"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna la instància (cached) de Settings. Carregada al primer import."""
    return Settings()
