"""Capa 1 del banc de proves: tests DETERMINISTES de la lògica RAG (sense LLM ni BD).

Cobreix les funcions pures que defineixen el comportament citable de SigPhi:
  - split_suggestions  : separació del bloc [[SUGGESTIONS]] (regla 21)
  - _is_followup       : detecció de seguiments (canvi d'idioma, "explica més"…)
  - caveats            : avisos de discriminació / context / completesa-autoria
  - get_sources        : marca ⚠ a les fonts fragmentàries o discriminatòries
"""
from __future__ import annotations

from app.domain.caveats import (
    classify,
    discriminatory_warning,
    historical_context_note,
)
from app.domain.models import Chunk, RetrievedChunk
from app.services.chat import _is_followup, get_sources, split_suggestions


# ───────────────────────── split_suggestions (regla 21) ─────────────────────────

def test_split_suggestions_extracts_three():
    text = "Resposta amb cites.\n\n[[SUGGESTIONS]]\n- Pregunta 1\n- Pregunta 2\n- Pregunta 3"
    answer, sugg = split_suggestions(text)
    assert answer == "Resposta amb cites."
    assert sugg == ["Pregunta 1", "Pregunta 2", "Pregunta 3"]


def test_split_suggestions_none_when_absent():
    text = "Una resposta normal sense bloc."
    answer, sugg = split_suggestions(text)
    assert answer == text
    assert sugg == []


def test_split_suggestions_caps_at_three():
    text = "R.\n[[SUGGESTIONS]]\n- A\n- B\n- C\n- D\n- E"
    _, sugg = split_suggestions(text)
    assert sugg == ["A", "B", "C"]


def test_split_suggestions_tolerates_single_bracket_and_numbering():
    text = "R.\n[SUGGESTIONS]\n1. Una\n2) Dos"
    _, sugg = split_suggestions(text)
    assert sugg == ["Una", "Dos"]


# ───────────────────────────── _is_followup ─────────────────────────────────────

def test_followup_language_request():
    assert _is_followup("en català")
    assert _is_followup("in english")
    assert _is_followup("tradueix-ho")


def test_followup_meta_keyword():
    assert _is_followup("explica més")
    assert _is_followup("per què?")


def test_not_followup_for_substantive_question():
    assert not _is_followup("Què deia Plató sobre la justícia a la República?")
    assert not _is_followup("")


# ───────────────────────────── caveats / discriminació ──────────────────────────

def test_discriminatory_work_level_always_fires():
    # Luther sobre els jueus: discriminació pervasiva (triggers=None) -> avisa sempre.
    assert discriminatory_warning("Martin Luther", "On the Jews and Their Lies", "")
    assert discriminatory_warning("Laws of Manu", "Laws of Manu", "")


def test_discriminatory_passage_level_needs_trigger():
    # Aristòtil Política: només avisa si el fragment conté el passatge de l'esclavitud.
    work = "Politics A Treatise on Government"
    assert discriminatory_warning("Aristotle", work, "he is a slave by nature")
    assert discriminatory_warning("Aristotle", work, "the weather today is mild") is None


def test_historical_context_note_fascism():
    assert historical_context_note("Giovanni Gentile", "La dottrina del fascismo", "")
    assert historical_context_note("Plato", "The Republic", "") is None


def test_classify_authorship_and_completeness():
    assert classify("Confucius", "The Analects")[1] == "Recorded/compiled by others"
    assert classify("Heraclitus", "Fragments")[0] == "Fragments only"
    assert classify("Laozi", "Tao Te Ching")[1] == "Attributed (authorship debated)"
    assert classify("Some Author", "Extracts from the Ethics")[0] == "Selection / partial"
    assert classify("Plato", "The Republic") == ("Complete work", "Written by the author", "—")


# ───────────────────────────── get_sources (marca ⚠) ────────────────────────────

def _rc(author, work, text="", note="—", completeness="Complete work", score=0.8):
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=f"{work}#0", text=text, author=author, work=work, language="English",
            completeness=completeness, authorship="Written by the author", note=note,
        ),
        score=score,
    )


def test_get_sources_plain():
    srcs = get_sources([_rc("Plato", "The Republic", "justice is…")])
    assert srcs == ["Plato — The Republic"]


def test_get_sources_flags_discriminatory():
    srcs = get_sources([_rc("Martin Luther", "On the Jews and Their Lies", "burn the synagogues")])
    assert len(srcs) == 1
    assert "⚠" in srcs[0] and "discriminatori" in srcs[0]


def test_get_sources_flags_fragmentary():
    srcs = get_sources([
        _rc("Heraclitus", "Fragments", "the way up", note="Only fragments survive.",
            completeness="Fragments only")
    ])
    assert "⚠" in srcs[0]
    assert "fragments only" in srcs[0]


def test_get_sources_deduplicates():
    rcs = [_rc("Plato", "The Republic", "a"), _rc("Plato", "The Republic", "b")]
    assert get_sources(rcs) == ["Plato — The Republic"]
