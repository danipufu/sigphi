"""Tests per a les funcions de neteja de text de scripts/ingest.py."""
from __future__ import annotations

from scripts.ingest import strip_gutenberg_boilerplate, strip_perseus_frontmatter

# --- strip_gutenberg_boilerplate -------------------------------------------

_PG_BODY = """\
The Project Gutenberg eBook of Foo

This ebook is for the use of anyone anywhere...

*** START OF THE PROJECT GUTENBERG EBOOK FOO ***

Produced by John Smith

CHAPTER I
The actual philosophical text begins here and continues for many pages.
It is the only part that should reach the embeddings.

CHAPTER II
More philosophical content.

            *** END OF THE PROJECT GUTENBERG EBOOK FOO ***

Updated editions will replace the previous one—the old editions will
be renamed.
"""

_PG_BODY_THIS = """\
*** START OF THIS PROJECT GUTENBERG EBOOK BAR ***
Actual text.
*** END OF THIS PROJECT GUTENBERG EBOOK BAR ***
Footer.
"""


def test_pg_strips_header_and_footer():
    result = strip_gutenberg_boilerplate(_PG_BODY)
    assert "Project Gutenberg eBook" not in result
    assert "*** START OF" not in result
    assert "*** END OF" not in result
    assert "Updated editions" not in result


def test_pg_keeps_body():
    result = strip_gutenberg_boilerplate(_PG_BODY)
    assert "CHAPTER I" in result
    assert "philosophical text begins here" in result
    assert "CHAPTER II" in result


def test_pg_variant_this():
    result = strip_gutenberg_boilerplate(_PG_BODY_THIS)
    assert "Actual text." in result
    assert "Footer." not in result
    assert "*** START OF" not in result


def test_pg_idempotent():
    once = strip_gutenberg_boilerplate(_PG_BODY)
    twice = strip_gutenberg_boilerplate(once)
    assert once == twice


def test_pg_noop_on_non_pg_text():
    text = "Just a normal philosophical text with no Gutenberg markers."
    assert strip_gutenberg_boilerplate(text) == text


def test_pg_indented_end_marker():
    """El marcador END pot tenir espais inicials (cas real de Xenophon Memorabilia)."""
    body = "Text real.\n\n            *** END OF THE PROJECT GUTENBERG EBOOK X ***\n\nFooter."
    result = strip_gutenberg_boilerplate(body)
    assert "Text real." in result
    assert "Footer." not in result
    assert "*** END OF" not in result
