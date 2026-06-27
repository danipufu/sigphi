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


# --- strip_mediawiki_markup (conservador: NO toca taules) -------------------

from scripts.ingest import strip_mediawiki_markup


def test_mw_html_entities():
    assert strip_mediawiki_markup("a &nbsp; b &amp; c &shy;d") == "a   b & c d"


def test_mw_internal_links():
    assert strip_mediawiki_markup("see [[Plato|the sage]] now") == "see the sage now"
    assert strip_mediawiki_markup("[[Stoicism]] rocks") == "Stoicism rocks"


def test_mw_category_and_templates_removed():
    assert strip_mediawiki_markup("[[Category:Stoics]] body").strip() == "body"
    assert strip_mediawiki_markup("{{cite|a=1}}word") == "word"


def test_mw_emphasis_stripped():
    assert strip_mediawiki_markup("'''bold''' and ''italic''") == "bold and italic"


def test_mw_external_link_keeps_text():
    assert strip_mediawiki_markup("[https://x.org/y Index here]") == "Index here"


def test_mw_table_content_preserved_skeleton_removed():
    # CLAU: el text de les cel·les (vers/drama) es conserva; l'esquelet de taula es treu.
    src = "{|\n|-\n| Magnum ingenium Luculli\n|}"
    out = strip_mediawiki_markup(src)
    assert "Magnum ingenium Luculli" in out
    assert "{|" not in out and "|}" not in out


def test_mw_inline_cell_verse_preserved():
    # Cel·la en línia "||" amb vers (cas Seneca Thyestes).
    out = strip_mediawiki_markup("|| Quis inferorum sede ab infausta extrahit")
    assert out == "Quis inferorum sede ab infausta extrahit"


def test_mw_styled_cell_keeps_content():
    out = strip_mediawiki_markup('| style="text-align:right" | actual content')
    assert out == "actual content"


def test_mw_orphan_template_fragment_removed():
    # Plantilla de Wikisource no expandida que deixa tancament + paràmetre orfes.
    src = "Real letter body here.\n\n |translation = \n}}"
    out = strip_mediawiki_markup(src)
    assert "Real letter body here." in out
    assert "}}" not in out and "translation =" not in out


def test_mw_anchor_link_with_nested_brackets():
    # [[#àncora|text [QQ. 6-17]]] -> conserva el text, treu els claudàtors dobles.
    out = strip_mediawiki_markup("(1) [[#The Nature|What makes a human act? [QQ. 6-17]]]")
    assert "What makes a human act?" in out
    assert "[[" not in out and "]]" not in out


def test_mw_double_braces_removed():
    assert strip_mediawiki_markup("text }}}} more") == "text  more"


def test_mw_noop_on_plain_prose():
    assert strip_mediawiki_markup("Plain Latin prose here") == "Plain Latin prose here"


# --- clean_residual_markup (universal: entitats HTML + claudàtors, qualsevol font) ---

from scripts.ingest import clean_residual_markup


def test_cr_decodes_numeric_entities():
    # marxists.org: cometes/guions tipogràfics com a entitats numèriques.
    out = clean_residual_markup("workers&#8217; &#8220;mass action&#8221;")
    assert "&#" not in out and "workers" in out


def test_cr_decodes_named_entities():
    assert clean_residual_markup("Marx &amp; Engels") == "Marx & Engels"


def test_cr_strips_page_brackets():
    assert clean_residual_markup("leaf [[page 2]] closes") == "leaf page 2 closes"


def test_cr_strips_midline_table_noise():
    # soroll d'OCR llatí/grec: {| |} enmig de línia.
    assert "{|" not in clean_residual_markup("medicina {| quod |} corpus")


def test_cr_noop_on_clean_prose():
    assert clean_residual_markup("Plain prose with no markup.") == "Plain prose with no markup."
