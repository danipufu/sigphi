"""Tests de GeminiLLM.generate_stream(): l'avís de resposta interrompuda quan
el stream falla A MITGES (després d'haver emès contingut real). No toca
Gemini de veritat: substitueix el client intern (_llm) per un doble fals
DESPRÉS de construir, ja que ChatGoogleGenerativeAI no valida credencials ni
fa cap crida de xarxa a __init__ (només desa la configuració)."""
from __future__ import annotations

from app.infrastructure.llm import GeminiLLM, _INTERRUPTED_NOTE, _INTERRUPTED_NOTE_DEFAULT


class _FakeChunk:
    """Simula AIMessageChunk: el codi real fa `full + chunk` per acumular."""

    def __init__(self, content: str) -> None:
        self.content = content

    def __add__(self, other: "_FakeChunk") -> "_FakeChunk":
        return _FakeChunk(self.content + other.content)


class _StreamThenFail:
    """Emet 2 fragments reals i després peta -- simula una connexió tallada
    a mitges (el cas real vist en producció: 503 UNAVAILABLE mig stream)."""

    def stream(self, messages):
        yield _FakeChunk("Seneca diu que ")
        yield _FakeChunk("la mort no fa por.")
        raise RuntimeError("503 UNAVAILABLE (simulat)")


class _FailImmediately:
    """Peta ABANS d'emetre res -- ha de reintentar, no avisar de tall."""

    def __init__(self) -> None:
        self.calls = 0

    def stream(self, messages):
        self.calls += 1
        raise RuntimeError("429 (simulat)")
        yield  # inabastable; fa d'aquest mètode un generador


def _llm() -> GeminiLLM:
    # api_key fictícia: ChatGoogleGenerativeAI no valida ni truca cap xarxa a
    # __init__, així que això no toca Gemini de veritat.
    return GeminiLLM(api_key="test-key-not-real")


def test_interrupted_mid_stream_appends_note_in_detected_language():
    inst = _llm()
    inst._llm = _StreamThenFail()
    chunks = list(inst.generate_stream("system", "Què deia Sèneca de la mort?", "context"))
    full = "".join(chunks)
    assert "Seneca diu que la mort no fa por." in full
    assert _INTERRUPTED_NOTE["Catalan"] in full


def test_interrupted_mid_stream_does_not_duplicate_content():
    inst = _llm()
    inst._llm = _StreamThenFail()
    chunks = list(inst.generate_stream("system", "Què deia Sèneca?", "context"))
    full = "".join(chunks)
    assert full.count("Seneca diu que") == 1  # no ha reintentat (duplicaria)


def test_interrupted_mid_stream_falls_back_to_english_for_undetected_language():
    inst = _llm()
    inst._llm = _StreamThenFail()
    # consulta sense senyals clars d'idioma -> ha de caure a l'anglès per defecte
    chunks = list(inst.generate_stream("system", "xyz 123", "context"))
    full = "".join(chunks)
    assert _INTERRUPTED_NOTE_DEFAULT in full


def test_failure_before_any_content_retries_instead_of_warning():
    inst = _llm()
    fake = _FailImmediately()
    inst._llm = fake
    chunks = list(inst.generate_stream("system", "Some question", "context"))
    full = "".join(chunks)
    assert fake.calls == 2  # ha reintentat (cap contingut emès encara)
    assert _INTERRUPTED_NOTE_DEFAULT not in full  # NO és l'avís de tall
    assert "busy" in full.lower() or "⏳" in full  # és LLM_BUSY_MSG final
