"""Baixa textos sagrats canònics en traducció de DOMINI PÚBLIC (Project Gutenberg),
els neteja (treu la capçalera/peu legal de Gutenberg) i els desa a corpus/ amb
capçalera SIGPHI: autor, obra, idioma + un caveat NEUTRAL (centrat en traducció i
transmissió textual, mai en la validesa religiosa).

Després, re-ingest (resumible, només els nous):  bash deploy/run_ingest.sh

Ús (al VPS, des de l'arrel):  python scripts/download_sacred.py
"""
from __future__ import annotations
import re
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# (gutenberg_id, author, work, language, completeness, authorship, note, filename)
TEXTS = [
    (10, "Bible", "The Holy Bible (King James Version)", "English",
     "Complete work", "Anonymous / composite",
     "Antologia de molts textos i autors recopilats al llarg de segles; "
     "versió King James (traducció anglesa de 1611), no els originals hebreu/grec.",
     "Bible__The_Holy_Bible_KJV_en.txt"),
    (2800, "Quran", "The Qur'an", "English",
     "Complete work", "Recorded/compiled by others",
     "Text sagrat de l'islam transmès i compilat pels seguidors de Mahoma; "
     "aquesta és una traducció anglesa (Rodwell, 1861), no l'àrab original.",
     "Quran__The_Quran_Rodwell_en.txt"),
    (2388, "Bhagavad Gita", "Bhagavad Gita (The Song Celestial)", "English",
     "Complete work", "Attributed (authorship debated)",
     "Episodi del poema èpic Mahabharata, tradicionalment atribuït a Vyasa; "
     "traducció poètica anglesa d'Edwin Arnold (1885), no el sànscrit original.",
     "Bhagavad_Gita__The_Song_Celestial_en.txt"),
    (2017, "Dhammapada", "The Dhammapada", "English",
     "Complete work", "Recorded/compiled by others",
     "Antologia de versos de la tradició budista, compilats pels deixebles; "
     "traducció anglesa de Max Müller (1881), no el pali original.",
     "Dhammapada__The_Dhammapada_en.txt"),

    # --- Lot 2 ---
    (4094, "Confucius",
     "The Four Books I: Analects, Great Learning, Doctrine of the Mean (Legge)",
     "English", "Complete work", "Recorded/compiled by others",
     "Clàssics confucians recollits i compilats pels deixebles; traducció de "
     "James Legge, no el xinès original.",
     "Confucius__The_Four_Books_I_Legge_en.txt"),
    (3283, "Upanishads", "The Upanishads", "English",
     "Selection / partial", "Anonymous / composite",
     "Textos vèdics de transmissió oral i autoria anònima; traducció anglesa, "
     "no el sànscrit original.",
     "Upanishads__The_Upanishads_en.txt"),
    (2526, "Patanjali", "The Yoga Sutras of Patanjali", "English",
     "Complete work", "Attributed (authorship debated)",
     "Aforismes atribuïts a Patañjali; traducció de Charles Johnston, no el "
     "sànscrit original.",
     "Patanjali__The_Yoga_Sutras_en.txt"),

    # --- Lot 3 ---
    (9394, "Shijing", "The Book of Poetry (Shih King, Legge)", "English",
     "Complete work", "Anonymous / composite",
     "Antologia de poemes de la Xina antiga, compilació anònima; un dels Cinc "
     "Clàssics confucians; traducció de James Legge, no el xinès original.",
     "Shijing__The_Book_of_Poetry_Legge_en.txt"),
    (18897, "Gilgamesh", "The Epic of Gilgamesh", "English",
     "Selection / partial", "Anonymous / composite",
     "Poema èpic mesopotàmic conservat en tauletes cuneïformes, autoria anònima; "
     "versió parcial de Langdon, no l'accadi original.",
     "Gilgamesh__The_Epic_of_Gilgamesh_en.txt"),
    (73533, "Poetic Edda", "The Poetic Edda", "English",
     "Complete work", "Anonymous / composite",
     "Poemes de la mitologia nòrdica de transmissió oral i autoria anònima; "
     "traducció de Bellows, no l'islandès original.",
     "Poetic_Edda__The_Poetic_Edda_en.txt"),
    (18947, "Snorri Sturluson", "The Prose Edda (Younger Edda)", "English",
     "Complete work", "Written by the author",
     "Compilació de la mitologia nòrdica per Snorri Sturluson (s.XIII); "
     "traducció anglesa, no l'islandès original.",
     "Snorri_Sturluson__The_Prose_Edda_en.txt"),
    (348, "Hesiod", "Theogony and Works and Days", "English",
     "Complete work", "Written by the author",
     "Poemes d'Hesíode (s.VIII aC); traducció d'Evelyn-White, no el grec "
     "original (el volum inclou també els himnes homèrics).",
     "Hesiod__Theogony_and_Works_and_Days_en.txt"),

    # --- Autors hispànics disponibles a Gutenberg ---
    (62691, "Baltasar Gracian", "El Criticón (tom 1)", "Spanish",
     "Complete work", "Written by the author", "—",
     "Baltasar_Gracian__El_Criticon_1_es.txt"),
    (63402, "Baltasar Gracian", "El Criticón (tom 2)", "Spanish",
     "Complete work", "Written by the author", "—",
     "Baltasar_Gracian__El_Criticon_2_es.txt"),
    (20321, "Bartolome de las Casas",
     "A Brief Account of the Destruction of the Indies", "English",
     "Complete work", "Written by the author",
     "Traducció anglesa de l'original castellà (1552).",
     "Las_Casas__Brief_Account_Destruction_Indies_en.txt"),

    # --- Lot 4: Mahabharata complet (trad. en prosa de Ganguli, 4 volums) ---
    (15474, "Mahabharata",
     "The Mahabharata, Vol. I (Books 1-3: Adi, Sabha, Vana) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit tradicionalment atribuït a Vyasa, compost i ampliat al "
     "llarg de segles; traducció en prosa de Kisari Mohan Ganguli (1883-96), no el "
     "sànscrit original. Volum I de IV (llibres 1-3).",
     "Mahabharata__Ganguli_Vol1_en.txt"),
    (15475, "Mahabharata",
     "The Mahabharata, Vol. II (Books 4-7: Virata...Drona) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Vyasa; traducció en prosa de K. M. Ganguli, "
     "no el sànscrit original. Volum II de IV (llibres 4-7; inclou la Bhagavad Gita "
     "en prosa dins el Bhishma Parva).",
     "Mahabharata__Ganguli_Vol2_en.txt"),
    (15476, "Mahabharata",
     "The Mahabharata, Vol. III (Books 8-12) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Vyasa; traducció en prosa de K. M. Ganguli, "
     "no el sànscrit original. Volum III de IV (llibres 8-12).",
     "Mahabharata__Ganguli_Vol3_en.txt"),
    (15477, "Mahabharata",
     "The Mahabharata, Vol. IV (Books 13-18) — Ganguli", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Vyasa; traducció en prosa de K. M. Ganguli, "
     "no el sànscrit original. Volum IV de IV (llibres 13-18).",
     "Mahabharata__Ganguli_Vol4_en.txt"),

    # --- Lot 5: hispànics i analítics (Gutenberg) ---
    (28929, "Jaime Balmes", "El Criterio", "Spanish",
     "Complete work", "Written by the author", "—",
     "Jaime_Balmes__El_Criterio_es.txt"),
]

_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)
_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)


def fetch(gid: int) -> str | None:
    urls = [
        f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt",
        f"https://www.gutenberg.org/files/{gid}/{gid}.txt",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SigPhi)"})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1")  # edicions Gutenberg antigues (ISO-8859-1)
        except Exception:
            continue
    return None


def strip_gutenberg(text: str) -> str:
    m = _START.search(text)
    if m:
        text = text[m.end():]
    m = _END.search(text)
    if m:
        text = text[:m.start()]
    return text.strip()


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    ok = 0
    for gid, author, work, lang, comp, auth, note, fname in TEXTS:
        dest = CORPUS / fname
        if dest.exists():
            print(f"[skip] ja existeix: {fname}")
            ok += 1
            continue
        print(f"[baixant] {work} (Gutenberg #{gid})...")
        raw = fetch(gid)
        if not raw:
            print(f"   ERROR: no s'ha pogut baixar #{gid}")
            continue
        body = strip_gutenberg(raw)
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
    print(f"\n{ok}/{len(TEXTS)} textos a punt a corpus/.")
    print("Ara re-ingesta els nous (resumible):  bash deploy/run_ingest.sh")


if __name__ == "__main__":
    main()
