"""Punt d'entrada de SigPhi.

FastAPI amb:
  - lifespan: carrega el model d'embeddings i construeix els serveis UN sol cop
    (per això cal 1 sol worker d'uvicorn: amb més es duplicaria el model en RAM).
  - API REST a /api/* (chat, health) amb rate limiting per IP.
  - UI Gradio muntada a / (Opció B: FastAPI + Gradio al mateix procés).

Execució (VPS):  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import routes_chat, routes_health
from app.api.dependencies import limiter
from app.config import get_settings
from app.infrastructure.chunk_store import ChunkStore
from app.infrastructure.embedder import SentenceTransformersEmbedder
from app.infrastructure.llm import GeminiLLM
from app.infrastructure.vector_db import build_vector_db
from app.services.chat import ChatService
from app.services.retrieval import RetrievalService


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    embedder = SentenceTransformersEmbedder(s.embed_model)
    chunk_store = ChunkStore(s.chunk_store_path)
    vector_db = build_vector_db(s, chunk_store=chunk_store)
    llm = GeminiLLM(s.google_api_key, model=s.gemini_model)
    retrieval = RetrievalService(embedder, vector_db, s.aliases_path, top_k=s.top_k)

    app.state.chunk_store = chunk_store
    app.state.chat_service = ChatService(llm, retrieval)
    yield
    chunk_store.close()


def _history_to_tuples(history) -> list[tuple[str, str]]:
    """Adapta l'historial de Gradio (format 'messages' o 'tuples') a tuples."""
    tuples: list[tuple[str, str]] = []
    if not history:
        return tuples
    if isinstance(history[0], dict):  # format "messages"
        pending = None
        for m in history:
            role, content = m.get("role"), m.get("content", "")
            if role == "user":
                pending = content
            elif role == "assistant" and pending is not None:
                tuples.append((pending, content))
                pending = None
    else:  # format "tuples" [[user, assistant], ...]
        for pair in history:
            if len(pair) == 2:
                tuples.append((pair[0], pair[1]))
    return tuples


def _build_gradio(app: FastAPI) -> gr.Blocks:
    def respond(message, history):
        chat_service = app.state.chat_service
        res = chat_service.answer(message, _history_to_tuples(history))
        if res.sources:
            srcs = "\n".join(f"- {s}" for s in res.sources)
            return f"{res.answer}\n\n---\n**Fonts:**\n{srcs}"
        return res.answer

    return gr.ChatInterface(
        fn=respond,
        type="messages",
        title="SigPhi — Filosofia des de fonts primàries",
        description=(
            "Respon NOMÉS amb textos filosòfics primaris de domini públic, amb "
            "cites verificables. Pots preguntar en qualsevol idioma."
        ),
    )


def build_app() -> FastAPI:
    app = FastAPI(title="SigPhi", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(routes_health.router)
    app.include_router(routes_chat.router)
    demo = _build_gradio(app)
    app = gr.mount_gradio_app(app, demo, path="/")
    return app


app = build_app()
