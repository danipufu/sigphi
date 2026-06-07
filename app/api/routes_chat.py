"""Endpoint REST de xat RAG: POST /api/chat -> resposta + fonts citables."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_chat_service, limiter, rate_limit
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
