"""Baixa textos en DOMINI PÚBLIC d'Internet Archive (text complet OCR `_djvu.txt`),
neteja el soroll de l'OCR (salts de pàgina, espais sobrants) i els desa a corpus/
amb la MATEIXA capçalera SIGPHI que download_sacred.py (autor, obra, idioma + un
caveat NEUTRAL centrat en traducció/transmissió i en el fet que és una
digitalització OCR; mai en la validesa religiosa).

Per a fonts que NO són a Project Gutenberg (escriptura sij, I Ching de Legge,
Zend-Avesta de Darmesteter...). Internet Archive serveix el text complet a:
    https://archive.org/download/<identifier>/<fitxer>_djvu.txt
(el `urllib` segueix sol el redirect 302 cap al node de dades; el nom del fitxer
_djvu.txt no sempre coincideix amb l'identifier, per això es desa explícit).

Ús (al VPS, des de l'arrel):  python scripts/download_archive.py
"""
from __future__ import annotations
import re
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# (identifier, djvu_filename, author, work, language, completeness, authorship, note, out_filename)
TEXTS = [
    ("TheAdiGranthOrTheHolyScripturesOfTheSikhs",
     "TheAdiGranthOrTheHolyScripturesOfTheSikhs_djvu.txt",
     "Adi Granth", "The Adi Granth (Holy Scriptures of the Sikhs)", "English",
     "Selection / partial", "Recorded/compiled by others",
     "Escriptura sij compilada per Guru Arjan (1604) amb himnes dels gurus sikhs i "
     "de diversos bhagats; traducció anglesa parcial d'Ernest Trumpp (1877), no el "
     "gurmukhi original. Digitalització OCR d'Internet Archive.",
     "Adi_Granth__Trumpp_en.txt"),
    ("iching00jame", "iching00jame_djvu.txt",
     "I Ching", "The I Ching (Book of Changes)", "English",
     "Complete work", "Anonymous / composite",
     "Clàssic xinès endevinatori i filosòfic, de formació anònima i composta (nucli "
     "Zhou Yi més les 'Deu Ales' atribuïdes a Confuci); traducció de James Legge "
     "(1882, SBE vol. XVI), no el xinès original. Digitalització OCR.",
     "I_Ching__Legge_en.txt"),
    ("in.ernet.dli.2015.500448", "2015.500448.The-Zend-Avesta_djvu.txt",
     "Avesta", "The Zend-Avesta, Part I: The Vendidad (SBE vol. IV)", "English",
     "Selection / partial", "Anonymous / composite",
     "Escriptura zoroastriana; aquest volum és la Part I (el Vendidad), de composició "
     "sacerdotal; traducció de James Darmesteter (1880, SBE vol. IV), no l'avèstic "
     "original. Digitalització OCR. Els Gathes, atribuïts a Zaratustra, són en altres volums.",
     "Avesta__Vendidad_Darmesteter_en.txt"),
]


def fetch(identifier: str, djvu: str) -> str | None:
    url = f"https://archive.org/download/{identifier}/{djvu}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SigPhi)"})
        with urllib.request.urlopen(req, timeout=180) as r:  # urllib segueix el 302
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"   ERROR baixant {identifier}: {e}")
        return None


def clean_ocr(text: str) -> str:
    text = text.replace("\x0c", "\n")        # marques de salt de pàgina DjVu
    text = re.sub(r"[ \t]+\n", "\n", text)   # espais a final de línia
    text = re.sub(r"\n{3,}", "\n\n", text)   # col·lapsa blocs de línies en blanc
    return text.strip()


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    ok = 0
    for ident, djvu, author, work, lang, comp, auth, note, fname in TEXTS:
        dest = CORPUS / fname
        if dest.exists():
            print(f"[skip] ja existeix: {fname}")
            ok += 1
            continue
        print(f"[baixant] {work} (archive.org/{ident})...")
        raw = fetch(ident, djvu)
        if not raw:
            continue
        body = clean_ocr(raw)
        if len(body) < 5000:
            print(f"   AVÍS: text molt curt ({len(body)} car.) -> revisa la font")
        header = (
            "=====SIGPHI=====\n"
            f"author: {author}\nwork: {work}\nlanguage: {lang}\n"
            f"completeness: {comp}\nauthorship: {auth}\nnote: {note}\n"
            "=====\n\n"
        )
        dest.write_text(header + body, encoding="utf-8")
        print(f"   OK -> {fname} ({len(body)//1024} KB)")
        ok += 1
    print(f"\n{ok}/{len(TEXTS)} textos d'archive.org a punt a corpus/.")
    print("Ara re-ingesta els nous (resumible):  bash deploy/run_ingest.sh")


if __name__ == "__main__":
    main()
