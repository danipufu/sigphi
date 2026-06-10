"""Baixa obres de Wikisource (text complet) via l'API de MediaWiki i les desa a
corpus/ amb la mateixa capçalera SIGPHI que els altres baixadors.

Per a obres que NOMÉS són a Wikisource (Kojiki; clàssics hispànics/catalans que no
són ni a Gutenberg ni amb OCR net a archive.org). Cada obra es defineix per
(lang, page_title). El text es treu de `action=parse&prop=text` (HTML renderitzat,
amb les transclusions expandides) i es neteja a text pla amb html.parser (stdlib,
cap dependència nova). Si la pàgina principal és un índex (TOC), se segueixen les
SUBPÀGINES (en ordre de document) i es concatenen; recursiu fins a 3 nivells.

Ús (al VPS, des de l'arrel):  python scripts/download_wikisource.py
"""
from __future__ import annotations
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
UA = "SigPhi/1.0 (philosophy RAG corpus; +https://github.com/danipufu/sigphi)"
MIN_FULL = 4000     # si la pàgina té menys text, la tractem com a índex (TOC)
MAX_SUBPAGES = 400  # límit de seguretat per obra
MAX_DEPTH = 3
SLEEP = 0.4         # cortesia amb l'API de Wikimedia

# (lang, page_title, author, work, language, completeness, authorship, note, out_filename)
TEXTS: list[tuple] = [
    ("en", "Kojiki (Chamberlain, 1882)",
     "Kojiki", "Kojiki (Records of Ancient Matters)", "English",
     "Complete work", "Recorded/compiled by others",
     "Crònica xintoista del Japó compilada per Ō no Yasumaro (712 dC); traducció "
     "anglesa de Basil Hall Chamberlain (1882), no el japonès clàssic original. Text "
     "de Wikisource.",
     "Kojiki__Chamberlain_en.txt"),
    ("es", "Las nacionalidades",
     "Pi i Margall", "Las nacionalidades", "Spanish",
     "Complete work", "Written by the author",
     "Obra de filosofia política federalista de Francisco Pi i Margall (1877). Text "
     "de Wikisource.",
     "Pi_i_Margall__Las_nacionalidades_es.txt"),
    ("es", "Teatro crítico universal",
     "Benito Feijoo", "Teatro crítico universal (selecció de discursos)", "Spanish",
     "Selection / partial", "Written by the author",
     "Selecció de discursos del Teatro crítico universal de Benito Jerónimo Feijoo "
     "(1726-1740). Text de Wikisource (els discursos transcrits).",
     "Feijoo__Teatro_critico_es.txt"),
    ("ca", "Regles de bona criança",
     "Francesc Eiximenis", "Regles de bona criança", "Catalan",
     "Selection / partial", "Written by the author",
     "Text del franciscà Francesc Eiximenis (s. XIV). Català medieval. Text de Wikisource.",
     "Eiximenis__Regles_de_bona_crianca_ca.txt"),
    ("ca", "Llibre compost per Fra Anselm Turmeda, ab la oracio de Sant Miquel, lo Jorn del Judici, la Oració de Sant Roch, y de Sant Sebastiá",
     "Anselm Turmeda", "Llibre de bons amonestaments", "Catalan",
     "Complete work", "Written by the author",
     "Obra moral en vers d'Anselm Turmeda (1398). Català medieval. Text de Wikisource.",
     "Turmeda__Bons_amonestaments_ca.txt"),
    ("ca", "Llibre de Disputació de l'Ase",
     "Anselm Turmeda", "Disputa de l'ase", "Catalan",
     "Complete work", "Written by the author",
     "Sàtira filosòfica d'Anselm Turmeda (1417-18). Text català de Wikisource.",
     "Turmeda__Disputa_de_l_ase_ca.txt"),
]

_SKIP_TAGS = {"script", "style", "sup", "table"}
_VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "col"}
_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote"}
_SKIP_CLASS_HINTS = (
    "mw-editsection", "noprint", "reference", "pagenum", "mw-references",
    "ws-noexport", "navigation", "mw-cite", "toc", "catlinks", "header",
    "headertemplate", "ws-header", "ws-footer", "printfooter", "mw-jump",
    "licen", "ws-summary", "mw-indicator", "dotted",  # cartells de llicència, etc.
)


class _Extractor(HTMLParser):
    """Treu el text visible, saltant scripts, notes, navegació i números de pàgina."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[tuple[str, bool]] = []
        self.skip = 0

    def _skip_tag(self, tag: str, attrs: list) -> bool:
        if tag in _SKIP_TAGS:
            return True
        cls = next((v for k, v in attrs if k == "class" and v), "")
        return any(h in cls for h in _SKIP_CLASS_HINTS)

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            if tag == "br" and not self.skip:
                self.out.append("\n")
            return
        is_skip = self._skip_tag(tag, attrs)
        self.stack.append((tag, is_skip))
        if is_skip:
            self.skip += 1

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and not self.skip:
            self.out.append("\n")

    def handle_endtag(self, tag):
        while self.stack:
            t, is_skip = self.stack.pop()
            if is_skip:
                self.skip -= 1
            if not self.skip and t in _BLOCK_TAGS:
                self.out.append("\n")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def get_text(self) -> str:
        return "".join(self.out)


def extract(html: str) -> str:
    p = _Extractor()
    p.feed(html)
    return p.get_text()


def clean(text: str) -> str:
    text = text.replace(" ", " ").replace("​", "")
    # Marcadors de pàgina de ProofreadPage (ex: "Pàgina:Obra (1889).djvu/3").
    text = re.sub(r"(?:Pàgina|Page|Página|Seite)\s*:\s*[^\n]*?\.djvu\s*/\s*\d+", "", text)
    text = re.sub(r"\[\d+\]", "", text)          # marques de nota residuals
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def api_parse(lang: str, title: str) -> str | None:
    url = (
        f"https://{lang}.wikisource.org/w/api.php?action=parse&prop=text"
        f"&page={urllib.parse.quote(title)}&format=json&formatversion=2&redirects=1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"   ERROR API {lang}:{title}: {e}")
        return None
    if "error" in data:
        return None
    return data.get("parse", {}).get("text", "")


def subpage_links(html: str, title: str) -> list[str]:
    """Enllaços a subpàgines (<title>/...) en ordre de document, sense duplicats.

    Els href venen URL-codificats (accents -> %xx), per això es descodifiquen ABANS
    de comparar amb el títol base (si no, les obres amb accent donarien 0 subpàgines).
    """
    base = title.replace(" ", "_") + "/"
    out: list[str] = []
    seen: set[str] = set()
    for href in re.findall(r'href="(/wiki/[^"]+)"', html):
        path = urllib.parse.unquote(href[len("/wiki/"):]).split("#")[0]
        if path.startswith(base):
            page = path.replace("_", " ")
            if page and page not in seen:
                seen.add(page)
                out.append(page)
    return out


def collect(lang: str, title: str, visited: set[str], depth: int = 0) -> str:
    if title in visited or depth > MAX_DEPTH:
        return ""
    visited.add(title)
    html = api_parse(lang, title)
    if not html:
        return ""
    text = clean(extract(html))
    subs = subpage_links(html, title)
    if len(text) >= MIN_FULL or not subs:
        return text
    # És un índex: segueix les subpàgines en ordre i concatena.
    parts = [text] if text else []
    for sub in subs[:MAX_SUBPAGES]:
        time.sleep(SLEEP)
        parts.append(collect(lang, sub, visited, depth + 1))
    return "\n\n".join(p for p in parts if p)


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    ok = 0
    for lang, title, author, work, language, comp, auth, note, fname in TEXTS:
        dest = CORPUS / fname
        if dest.exists():
            print(f"[skip] ja existeix: {fname}")
            ok += 1
            continue
        print(f"[baixant] {work} (wikisource {lang}: {title})...")
        body = collect(lang, title, set())
        if len(body) < 2000:
            print(f"   AVÍS: text molt curt ({len(body)} car.) -> revisa títol/estructura")
            if not body:
                continue
        header = (
            "=====SIGPHI=====\n"
            f"author: {author}\nwork: {work}\nlanguage: {language}\n"
            f"completeness: {comp}\nauthorship: {auth}\nnote: {note}\n"
            "=====\n\n"
        )
        dest.write_text(header + body, encoding="utf-8")
        print(f"   OK -> {fname} ({len(body)//1024} KB)")
        ok += 1
    print(f"\n{ok}/{len(TEXTS)} obres de Wikisource a punt a corpus/.")


if __name__ == "__main__":
    main()
