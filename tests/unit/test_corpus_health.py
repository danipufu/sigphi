"""Tests de les heurístiques pures de corpus_health (sense BD ni LLM)."""
from __future__ import annotations

from scripts.corpus_health import (
    clean_word_ratio,
    find_duplicate_titles,
    find_markup,
    looks_like_garbage,
)

# Mostra real de brossa d'OCR trobada el jun-2026 (Bergson "Creative evolution").
GARBAGE = "ae LD) ate | tees AR Lt) etek). ea) te ae oeehee sees Led ele he onl pd aa f % } r ; ; 4 7 : ? ; : . , c"
CLEAN_EN = "CREATIVE EVOLUTION BY HENRI BERGSON PROFESSOR AT THE COLLEGE DE FRANCE AUTHORIZED TRANSLATION BY ARTHUR MITCHELL"
LATIN = "O Tite si quid ego adiuero curamve levasso quae nunc te coquit et versat in pectore fixa ecquid erit praemi"


def test_garbage_is_flagged():
    assert looks_like_garbage(GARBAGE)
    assert clean_word_ratio(GARBAGE) < 0.4


def test_clean_prose_is_not_flagged():
    assert not looks_like_garbage(CLEAN_EN)
    assert clean_word_ratio(CLEAN_EN) > 0.6


def test_heuristic_is_language_agnostic():
    # El llatí (i altres idiomes de l'alfabet llatí/grec) NO s'ha de marcar com a brossa.
    assert not looks_like_garbage(LATIN)


def test_empty_text_is_not_garbage():
    assert clean_word_ratio("") == 1.0
    assert not looks_like_garbage("")


def test_case_only_duplicate_detected():
    pairs = find_duplicate_titles(["Creative Evolution", "Creative evolution"])
    assert len(pairs) == 1


def test_punctuation_duplicate_detected():
    pairs = find_duplicate_titles(["Pragmatism A New Name", "Pragmatism: A New Name"])
    assert len(pairs) == 1


def test_distinct_volumes_not_flagged():
    # Volums diferents de la mateixa obra NO són duplicats.
    works = ["Plutarch's Lives, Volume 1 (of 4)", "Plutarch's Lives, Volume 2 (of 4)"]
    assert find_duplicate_titles(works) == []


def test_distinct_works_not_flagged():
    works = ["The Prince", "Discourses on Livy", "History of Florence"]
    assert find_duplicate_titles(works) == []


# --- soroll de marcatge / boilerplate (el cas real del Cato de Wikisource) -------

def test_markup_wikisource_notoc_detected():
    # Text llatí NET amb marcatge de Wikisource: clean_word_ratio no el caça (és prosa),
    # però find_markup sí.
    cato = "__NOTOC__ = I = :O Tite, si quid ego adiuero curamve levasso quae nunc te coquit"
    assert not looks_like_garbage(cato)        # és prosa llatina -> NO és brossa
    assert "__NOTOC__" in find_markup(cato)    # ...però té marcatge


def test_markup_gutenberg_boilerplate_detected():
    gut = "The Project Gutenberg eBook of X. *** START OF THE PROJECT GUTENBERG EBOOK"
    found = find_markup(gut)
    assert "Project Gutenberg" in found and "*** START OF" in found


def test_markup_mediawiki_tables_detected():
    assert find_markup("See {| class=wikitable [[Category:Aristotle]] {{cite}}")


def test_markup_html_entities_detected():
    assert "HTML-entities" in find_markup("a &amp; b &lt; c &gt; d &quot; e")


def test_clean_prose_has_no_markup():
    assert find_markup("O Tite si quid ego adiuero curamve levasso quae nunc te coquit") == []
