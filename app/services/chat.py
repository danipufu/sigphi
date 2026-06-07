"""ChatService: orquestra el RAG end-to-end.

Flux: retrieve (amb filtre d'autor) -> munta context amb CAVEATS -> LLM genera
resposta fidel a les fonts -> recull la llista de fonts (amb avisos ⚠).
"""
from __future__ import annotations
from dataclasses import dataclass

from app.domain.interfaces import LLMInterface
from app.domain.models import RetrievedChunk
from app.services.prompts import NO_CORPUS_MESSAGE, SYSTEM_PROMPT
from app.services.retrieval import RetrievalService


@dataclass(frozen=True, slots=True)
class ChatResult:
    """Resultat d'un torn de xat: resposta + fonts citables + chunks crus."""
    answer: str
    sources: list[str]
    retrieved: list[RetrievedChunk]


def format_context(retrieved: list[RetrievedChunk]) -> str:
    """Munta el context per al LLM, amb capçalera i CAVEAT per bloc."""
    sections = []
    for r in retrieved:
        c = r.chunk
        header = f"Source: {c.author} — {c.work}"
        if c.language:
            header += f" ({c.language})"
        if c.note and c.note != "—":
            header += f"\nCAVEAT: {c.note}"
        sections.append(f"[{header}]\n{c.text}")
    return "\n\n---\n\n".join(sections)


def get_sources(retrieved: list[RetrievedChunk]) -> list[str]:
    """Llista de fonts úniques, amb marca ⚠ si són fragmentàries o no directes."""
    seen: set[str] = set()
    sources: list[str] = []
    for r in retrieved:
        c = r.chunk
        label = f"{c.author} — {c.work}".strip(" —") if c.author else c.work
        if c.note and c.note != "—":
            flags = []
            if c.completeness and c.completeness != "Complete work":
                flags.append(c.completeness.lower())
            if c.authorship and c.authorship != "Written by the author":
                flags.append(c.authorship.lower())
            if flags:
                label += f" [⚠ {'; '.join(flags)}]"
        if label not in seen:
            seen.add(label)
            sources.append(label)
    return sources


class ChatService:
    def __init__(
        self,
        llm: LLMInterface,
        retrieval: RetrievalService,
        max_history: int = 5,
    ) -> None:
        self._llm = llm
        self._retrieval = retrieval
        self._max_history = max_history

    def answer(
        self,
        query: str,
        history: list[tuple[str, str]] | None = None,
    ) -> ChatResult:
        retrieved = self._retrieval.retrieve(query)
        if not retrieved:
            return ChatResult(answer=NO_CORPUS_MESSAGE, sources=[], retrieved=[])
        context = format_context(retrieved)
        hist = (history or [])[-self._max_history :]
        text = self._llm.generate(SYSTEM_PROMPT, query, context, hist)
        sources = get_sources(retrieved)
        return ChatResult(answer=text, sources=sources, retrieved=retrieved)
