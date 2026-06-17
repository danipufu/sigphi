"""Baixa textos en DOMINI PÚBLIC que viuen en una sola pàgina HTML (p. ex.
Marxists.org), els neteja a text pla (html.parser, stdlib) traient els metadatos
de transcripció/font, i els desa a corpus/ amb la capçalera SIGPHI.

Per a obres que no són ni a Gutenberg, ni amb OCR a archive.org, ni a Wikisource.

Ús (al VPS, des de l'arrel):  python scripts/download_html.py
"""
from __future__ import annotations
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
UA = "SigPhi/1.0 (philosophy RAG corpus; +https://github.com/danipufu/sigphi)"

# (url, author, work, language, completeness, authorship, note, filename)
TEXTS = [
    ("https://www.marxists.org/archive/marx/works/1844/jewish-question/index.htm",
     "Karl Marx", "On the Jewish Question (Zur Judenfrage)", "English",
     "Complete work", "Written by the author",
     "Assaig de Karl Marx (1844); traducció anglesa de domini públic (Marxists.org), "
     "no l'alemany original.",
     "Karl_Marx__On_the_Jewish_Question_en.txt"),
    # Encíclics papals moderns (textos PD; font: papalencyclicals.net pàgines individuals HTML)
    ("https://www.papalencyclicals.net/pius09/p9ineff.htm",
     "Pius IX", "Ineffabilis Deus (1854)", "English",
     "Complete work", "Written by the author",
     "Butlla de Pius IX (8 des. 1854) que defineix dogmàticament la Immaculada Concepció "
     "de la Verge Maria. Text PD (1854). Papalencyclicals.net.",
     "Pius_IX__Ineffabilis_Deus_en.txt"),
    ("https://www.papalencyclicals.net/ben15/b15spiri.htm",
     "Benedict XV", "Spiritus Paraclitus (1920)", "English",
     "Complete work", "Written by the author",
     "Encíclica de Benet XV (15 set. 1920) sobre Sant Jeroni i els estudis bíblics, "
     "amb motiu del 1500è aniversari de la mort del Doctor Màxim. Text PD. Papalencyclicals.net.",
     "Benedict_XV__Spiritus_Paraclitus_en.txt"),
    ("https://www.papalencyclicals.net/pius11/p11morta.htm",
     "Pius XI", "Mortalium Animos (1928)", "English",
     "Complete work", "Written by the author",
     "Encíclica de Pius XI (6 gen. 1928) sobre la unitat de l'Església "
     "i els perills del moviment ecumènic modern. Text PD. Papalencyclicals.net.",
     "Pius_XI__Mortalium_Animos_en.txt"),
    ("https://www.papalencyclicals.net/pius11/p11rappr.htm",
     "Pius XI", "Divini Illius Magistri (1929)", "English",
     "Complete work", "Written by the author",
     "Encíclica de Pius XI (31 des. 1929) sobre l'educació cristiana de la joventut; "
     "drets i deures de l'Església, la família i l'Estat en matèria educativa. "
     "Text PD. Papalencyclicals.net.",
     "Pius_XI__Divini_Illius_Magistri_en.txt"),
    ("https://www.papalencyclicals.net/pius11/p11casti.htm",
     "Pius XI", "Casti Connubii (1930)", "English",
     "Complete work", "Written by the author",
     "Encíclica de Pius XI (31 des. 1930) sobre el matrimoni cristià, "
     "la família i la moral sexual; resposta als moviments de control de natalitat. "
     "Text PD. Papalencyclicals.net.",
     "Pius_XI__Casti_Connubii_en.txt"),
]

_SKIP = {"script", "style", "head", "title", "nav", "footer"}
_BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote"}


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag == "br":
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip:
            self.skip -= 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def strip_html(html: str) -> str:
    p = _Strip()
    p.feed(html)
    t = "".join(p.out)
    # Treu les línies de metadades típiques de Marxists.org / transcripció.
    t = re.sub(
        r"(?im)^\s*(written|source|first published|publisher|transcribed|html markup|"
        r"online version|translated|proofed|copyleft|transcription).*$",
        "",
        t,
    )
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")
    except Exception as e:
        print(f"   ERROR {url}: {e}")
        return None


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    ok = 0
    for url, author, work, lang, comp, auth, note, fname in TEXTS:
        dest = CORPUS / fname
        if dest.exists():
            print(f"[skip] ja existeix: {fname}")
            ok += 1
            continue
        print(f"[baixant] {work} ({url})...")
        html = fetch(url)
        if not html:
            continue
        body = strip_html(html)
        if len(body) < 2000:
            print(f"   AVÍS: text molt curt ({len(body)} car.) -> revisa la font")
            if not body:
                continue
        header = (
            "=====SIGPHI=====\n"
            f"author: {author}\nwork: {work}\nlanguage: {lang}\n"
            f"completeness: {comp}\nauthorship: {auth}\nnote: {note}\n"
            "=====\n\n"
        )
        dest.write_text(header + body, encoding="utf-8")
        print(f"   OK -> {fname} ({len(body)//1024} KB)")
        ok += 1
    print(f"\n{ok}/{len(TEXTS)} textos HTML a punt a corpus/.")


if __name__ == "__main__":
    main()
