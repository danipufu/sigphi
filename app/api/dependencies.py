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

# Rate limiter per IP (configurat a build_app + exception handler).
limiter = Limiter(key_func=get_remote_address)


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_chunk_store(request: Request) -> ChunkStore:
    return request.app.state.chunk_store


def rate_limit() -> str:
    """Valor del rate limit (callable perquè es resol en runtime des de settings)."""
    return get_settings().rate_limit
