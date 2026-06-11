"""Endpoint REST de xat RAG: POST /api/chat -> resposta + fonts citables."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_chat_service, get_chunk_store, limiter, rate_limit
from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.services.chat import ChatService

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    history: list[tuple[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(rate_limit)
def chat(
    request: Request,  # requerit per slowapi
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    res = chat_service.answer(body.query, body.history)
    return ChatResponse(answer=res.answer, sources=res.sources)


@router.get("/ask", response_model=ChatResponse)
@limiter.limit(rate_limit)
def ask(
    request: Request,  # requerit per slowapi
    q: str = Query(..., min_length=1, description="La pregunta"),
    key: str = Query("", description="Clau secreta (ASK_API_KEY)"),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """Variant GET del xat, protegida amb clau, per a verificació externa (eines
    que només fan GET). Desactivada si ASK_API_KEY és buit. Retorna 404 si la clau
    no és correcta (no revela que l'endpoint existeix)."""
    secret = get_settings().ask_api_key
    if not secret or key != secret:
        raise HTTPException(status_code=404, detail="Not Found")
    res = chat_service.answer(q, [])
    return ChatResponse(answer=res.answer, sources=res.sources)


@router.get("/catalog")
def catalog(chunk_store: ChunkStore = Depends(get_chunk_store)) -> dict:
    """Catàleg REAL (autors + obres) llegit de la base de dades indexada."""
    items = chunk_store.catalog()
    return {
        "total_authors": len(items),
        "total_works": sum(len(i["works"]) for i in items),
        "total_chunks": chunk_store.count(),
        "authors": items,
    }


@router.get("/sample")
def sample(
    author: str = Query(..., description="Autor exacte (del catàleg)"),
    work: str = Query("", description="Obra exacta (opcional)"),
    key: str = Query(""),
    n: int = Query(1, ge=1, le=3),
    chunk_store: ChunkStore = Depends(get_chunk_store),
) -> dict:
    """Inspecció del text REAL (primers fragments) d'una obra, per a control de
    qualitat (detectar portades, traductor, editorial, brossa). Protegit amb clau."""
    secret = get_settings().ask_api_key
    if not secret or key != secret:
        raise HTTPException(status_code=404, detail="Not Found")
    return {
        "author": author,
        "work": work,
        "samples": chunk_store.sample(author, work or None, n),
    }
