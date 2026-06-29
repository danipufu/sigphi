"""Dependències compartides de l'API: injecció de serveis + rate limiter.

Els serveis pesats (embedder, vector_db, llm...) es creen UN sol cop al lifespan
de main.py i es desen a app.state. Aquí només els exposem via Depends.
"""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.services.chat import ChatService

def _client_ip(request: Request) -> str:
    """IP real del client darrere el proxy invers (Caddy).

    Caddy reenvia la IP original a la capçalera X-Forwarded-For; si no hi és
    (accés directe a uvicorn), cau a l'adreça remota. Sense això, totes les
    peticions semblarien venir de Caddy (127.0.0.1) i el rate limit seria
    GLOBAL en comptes de per usuari.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


# Rate limiter per IP real del client (configurat a build_app + exception handler).
limiter = Limiter(key_func=_client_ip)


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_chunk_store(request: Request) -> ChunkStore:
    return request.app.state.chunk_store


def get_vector_db(request: Request):
    return request.app.state.vector_db


def get_usage_meter(request: Request):
    return request.app.state.usage_meter


def rate_limit() -> str:
    """Valor del rate limit (callable perquè es resol en runtime des de settings)."""
    return get_settings().rate_limit
