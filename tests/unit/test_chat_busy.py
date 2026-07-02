"""Tests que quan l'LLM falla (LLM_BUSY_MSG), ChatService NO mostra fonts ni
suggeriments d'una resposta que en realitat no existeix. Trobat en producció:
una crida real amb la quota exhaurida retornava el missatge de "servei
ocupat" PERÒ amb fonts i 3 suggeriments enganxats, com si hagués anat bé."""
from __future__ import annotations

from app.domain.interfaces import LLM_BUSY_MSG
from app.domain.models import Chunk, RetrievedChunk
from app.services.chat import ChatService


class _FakeRetrieval:
    def __init__(self, chunks):
        self._chunks = chunks

    def retrieve(self, query):
        return self._chunks

    def detect_authors(self, query):
        return []


class _BusyLLM:
    """Simula l'LLM esgotat: generate()/generate_stream() sempre retornen
    LLM_BUSY_MSG (com fa GeminiLLM després de 2 intents fallits)."""

    def __init__(self) -> None:
        self.suggestions_called = False

    def generate(self, *a, **kw):
        return LLM_BUSY_MSG

    def generate_stream(self, *a, **kw):
        yield LLM_BUSY_MSG

    def generate_suggestions(self, *a, **kw):
        # NO s'hauria de cridar mai quan la resposta principal ha fallat.
        self.suggestions_called = True
        return ["no hauria d'aparèixer"]


def _rc():
    return RetrievedChunk(
        chunk=Chunk(chunk_id="x#0", text="t", author="Seneca", work="Letters",
                    language="English", completeness="Complete work",
                    authorship="Written by the author", note="—"),
        score=0.8,
    )


def test_answer_hides_sources_and_suggestions_when_llm_busy():
    llm = _BusyLLM()
    svc = ChatService(llm, _FakeRetrieval([_rc()]))
    res = svc.answer("Què deia Sèneca de la mort?")
    assert res.answer == LLM_BUSY_MSG
    assert res.sources == []
    assert res.suggestions == []
    assert not llm.suggestions_called  # no s'ha gastat quota de suggeriments en va


def test_answer_stream_hides_sources_and_suggestions_when_llm_busy():
    llm = _BusyLLM()
    svc = ChatService(llm, _FakeRetrieval([_rc()]))
    gen = svc.answer_stream("Què deia Sèneca de la mort?")
    res = None
    while True:
        try:
            next(gen)
        except StopIteration as e:
            res = e.value
            break
    assert res.answer == LLM_BUSY_MSG
    assert res.sources == []
    assert res.suggestions == []
    assert not llm.suggestions_called
