"""Endpoint REST de xat RAG: POST /api/chat -> resposta + fonts citables."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import (
    get_chat_service,
    get_chunk_store,
    get_usage_meter,
    get_vector_db,
    limiter,
    rate_limit,
)
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
    suggestions: list[str] = Field(default_factory=list)
    # Cites "(Autor, Obra)" que el verificador determinista (app/services/
    # citations.py) NO ha pogut confirmar contra les fonts recuperades. Buida
    # en el cas normal; informativa (la resposta NO es reescriu). Útil per a
    # eval_golden.py i per a monitoratge extern.
    unverified_citations: list[str] = Field(default_factory=list)


def _to_response(res) -> ChatResponse:
    return ChatResponse(
        answer=res.answer,
        sources=res.sources,
        suggestions=res.suggestions,
        unverified_citations=[f"{c.author}, {c.work}" for c in res.unverified_citations],
    )


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(rate_limit)
def chat(
    request: Request,  # requerit per slowapi
    body: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return _to_response(chat_service.answer(body.query, body.history))


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
    return _to_response(chat_service.answer(q, []))


@router.get("/usage")
def usage(
    key: str = Query("", description="Clau secreta (ASK_API_KEY)"),
    meter=Depends(get_usage_meter),
) -> dict:
    """Despesa estimada de l'LLM del mes en curs (tokens, cost, pressupost restant).
    Protegit amb clau, per a monitoratge. Retorna 404 si la clau no és correcta."""
    secret = get_settings().ask_api_key
    if not secret or key != secret:
        raise HTTPException(status_code=404, detail="Not Found")
    return meter.snapshot(get_settings().monthly_budget_eur)


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


@router.get("/admin/remove")
def admin_remove(
    author: str = Query(..., description="Autor exacte (del catàleg)"),
    work_contains: str = Query("", description="Si es dóna, només obres que ho contenen; si no, TOT l'autor"),
    apply: int = Query(0, description="0 = dry-run (per defecte); 1 = esborra de debò"),
    key: str = Query(""),
    chunk_store: ChunkStore = Depends(get_chunk_store),
    vector_db=Depends(get_vector_db),
) -> dict:
    """Elimina (o mostra en dry-run) obres/autors mal classificats de la BD. Protegit
    amb clau. Permet fer la neteja remotament sense executar res al VPS. NO re-embed."""
    secret = get_settings().ask_api_key
    if not secret or key != secret:
        raise HTTPException(status_code=404, detail="Not Found")
    targets: list[tuple[str | None, list[str]]] = []
    if work_contains:
        for work in chunk_store.find_works(author, work_contains):
            ids = chunk_store.chunk_ids_of(author, work)
            if ids:
                targets.append((work, ids))
    else:
        ids = chunk_store.chunk_ids_of(author)
        if ids:
            targets.append((None, ids))
    if apply:
        for _, ids in targets:
            vector_db.delete_chunk_ids(ids)
            chunk_store.delete_ids(ids)
    return {
        "author": author,
        "work_contains": work_contains or None,
        "applied": bool(apply),
        "removed": [{"work": w or "(TOT L'AUTOR)", "chunks": len(ids)} for w, ids in targets],
        "total_chunks": sum(len(ids) for _, ids in targets),
    }
