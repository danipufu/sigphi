"""Tests del verificador determinista de cites (app/services/citations.py)."""
from __future__ import annotations

from app.domain.models import Chunk, RetrievedChunk
from app.services.citations import extract_citations, unverified_citations


def _rc(author, work, score=0.8):
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=f"{work}#0", text="", author=author, work=work, language="English",
            completeness="Complete work", authorship="Written by the author", note="—",
        ),
        score=score,
    )


# --- extract_citations: reconeix cites reals, ignora incisos de prosa --------

def test_extract_simple_citation():
    cs = extract_citations("Seneca held that death is nothing (Seneca, Letters).")
    assert len(cs) == 1
    assert cs[0].author == "Seneca" and cs[0].work == "Letters" and cs[0].section is None


def test_extract_citation_with_locator():
    cs = extract_citations("As Kant argues (Kant, Critique of Pure Reason, Book II).")
    assert len(cs) == 1
    assert cs[0].section == "Book II"


def test_extract_multiple_citations_same_parens():
    cs = extract_citations(
        "For Kant, X (Kant, Critique of Pure Reason; Hegel, Phenomenology of Spirit)."
    )
    assert {c.author for c in cs} == {"Kant", "Hegel"}


def test_extract_multiple_citations_separate_sentences():
    text = (
        "Epictetus argues X (Epictetus, The Teaching of Epictetus). "
        "He also says Y (Epictetus, The Golden Sayings of Epictetus, with the Hymn of Cleanthes)."
    )
    cs = extract_citations(text)
    assert len(cs) == 2


def test_extract_ignores_prose_aside_that_is():
    # Cas real que temia: "(that is, ...)" té coma però NO és una cita.
    cs = extract_citations("The soul (that is, the seat of reason) is immortal.")
    assert cs == []


def test_extract_ignores_prose_aside_ie():
    cs = extract_citations("Pleasure (i.e., the absence of pain) is the goal.")
    assert cs == []


def test_extract_ignores_parenthetical_percentage_or_number():
    cs = extract_citations("The passage scores highly (relevance: 87%) on this topic.")
    assert cs == []


def test_extract_allows_name_particles():
    cs = extract_citations("As he wrote (Thomas a Kempis, The Imitation of Christ).")
    assert len(cs) == 1 and cs[0].author == "Thomas a Kempis"


# --- unverified_citations: detecta fabricacions, tolera variants legítimes --

def test_unverified_flags_fabricated_author():
    retrieved = [_rc("Seneca", "Letters")]
    answer = "This claim appears in the sources (Nietzsche, Beyond Good and Evil)."
    bad = unverified_citations(answer, retrieved)
    assert len(bad) == 1 and bad[0].author == "Nietzsche"


def test_unverified_flags_fabricated_work_of_known_author():
    retrieved = [_rc("Seneca", "Letters")]
    answer = "Seneca discusses this (Seneca, On the Shortness of Life)."
    bad = unverified_citations(answer, retrieved)
    assert len(bad) == 1


def test_unverified_passes_real_citation():
    retrieved = [_rc("Seneca", "Letters")]
    answer = "Seneca held that death is nothing to fear (Seneca, Letters)."
    assert unverified_citations(answer, retrieved) == []


def test_unverified_tolerates_shortened_title():
    # El model escurça "Critique of Pure Reason" a "Critique" -> legítim.
    retrieved = [_rc("Kant", "Critique of Pure Reason")]
    answer = "Kant argues this (Kant, Critique)."
    assert unverified_citations(answer, retrieved) == []


def test_unverified_tolerates_expanded_title_with_locator():
    retrieved = [_rc("Epictetus", "The Teaching of Epictetus")]
    answer = "He says X (Epictetus, The Teaching of Epictetus, Book I)."
    assert unverified_citations(answer, retrieved) == []


def test_unverified_multi_author_all_real():
    retrieved = [_rc("Kant", "Critique of Pure Reason"), _rc("Hegel", "Phenomenology of Spirit")]
    answer = "Compare Kant (Kant, Critique of Pure Reason) and Hegel (Hegel, Phenomenology of Spirit)."
    assert unverified_citations(answer, retrieved) == []


def test_unverified_multi_author_one_fabricated():
    retrieved = [_rc("Kant", "Critique of Pure Reason")]
    answer = "Compare Kant (Kant, Critique of Pure Reason) and Sartre (Sartre, Being and Nothingness)."
    bad = unverified_citations(answer, retrieved)
    assert len(bad) == 1 and bad[0].author == "Sartre"


def test_unverified_empty_when_no_citations():
    assert unverified_citations("Hello, how can I help you today?", []) == []
