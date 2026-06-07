"""Health check: confirma que l'app és viva i quants chunks té el ChunkStore."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_chunk_store
from app.infrastructure.chunk_store import ChunkStore

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(chunk_store: ChunkStore = Depends(get_chunk_store)) -> dict:
    try:
        n = chunk_store.count()
    except Exception:
        n = -1
    return {"status": "ok", "chunks": n}
