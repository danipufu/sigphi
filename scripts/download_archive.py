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
import time
import urllib.parse
import urllib.request
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# Per a miralls de Project Gutenberg allotjats a archive.org: treure capçalera/peu legal.
_GUT_START = re.compile(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)
_GUT_END = re.compile(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.I | re.S)

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

    # --- Lot 5 ---
    ("kautilyasarthash00sham", "kautilyasarthash00sham_djvu.txt",
     "Kautilya", "Arthashastra (Treatise on Statecraft)", "English",
     "Complete work", "Written by the author",
     "Tractat sànscrit de política i economia atribuït a Kautilya (Chanakya, s. IV aC); "
     "traducció de R. Shamasastry (1915), no el sànscrit original. Digitalització OCR.",
     "Kautilya__Arthashastra_Shamasastry_en.txt"),
    ("ideariumespaol01gani", "ideariumespaol01gani_djvu.txt",
     "Angel Ganivet", "Idearium español", "Spanish",
     "Complete work", "Written by the author",
     "Assaig d'Ángel Ganivet (1897). Digitalització OCR de l'edició original; "
     "pot contenir errades de reconeixement de text.",
     "Angel_Ganivet__Idearium_espanol_es.txt"),
    ("in.ernet.dli.2015.495279", "2015.495279.THA-SACRED_djvu.txt",
     "Avesta", "The Zend-Avesta, Part III: Yasna, Visparad, Gathas (SBE vol. XXXI)",
     "English", "Selection / partial", "Anonymous / composite",
     "Escriptura zoroastriana; Part III: el Yasna i sobretot els Gathes, himnes "
     "atribuïts directament a Zaratustra (el nucli més antic); traducció de L. H. Mills "
     "(1887, SBE vol. XXXI), no l'avèstic original. Digitalització OCR.",
     "Avesta__Yasna_Gathas_Mills_en.txt"),
    ("LesProlegomenesDIbnKhaldounVolume1",
     "Les Prolégomènes d'Ibn Khaldoun - Volume 1_djvu.txt",
     "Ibn Khaldun", "Les Prolégomènes (Muqaddimah), Volume I", "French",
     "Selection / partial", "Written by the author",
     "Introducció a la història universal d'Ibn Khaldun (1377); traducció francesa "
     "de W. M. de Slane (1863), no l'àrab original. Volum I de III. Digitalització OCR.",
     "Ibn_Khaldun__Prolegomenes_Vol1_de_Slane_fr.txt"),
    # Wittgenstein: el #5740 de Gutenberg NO té .txt directe (només PDF/TeX); fem
    # servir el mirall del text net de Gutenberg allotjat a Internet Archive.
    ("tractatuslogicop05740gut", "tloph10.txt",
     "Ludwig Wittgenstein", "Tractatus Logico-Philosophicus (Ogden)", "English",
     "Complete work", "Written by the author",
     "Traducció anglesa de C. K. Ogden (1922) del Tractatus (original alemany de 1921). "
     "Text de Project Gutenberg (#5740) via mirall d'Internet Archive.",
     "Wittgenstein__Tractatus_Ogden_en.txt"),

    # --- Lot 6 ---
    ("zendavesta02darm", "zendavesta02darm_djvu.txt",
     "Avesta", "The Zend-Avesta, Part II: Sirozahs, Yasts, Nyayis (SBE vol. XXIII)",
     "English", "Selection / partial", "Anonymous / composite",
     "Escriptura zoroastriana; Part II: els Yasts (himnes a divinitats) i els Sirozahs; "
     "traducció de James Darmesteter (1883, SBE vol. XXIII), no l'avèstic original. "
     "Digitalització OCR.",
     "Avesta__Yasts_Darmesteter_en.txt"),
    ("AlMuqaddimaIntroductionALhistoireUniverselleLesProlegomenesDIbnKhaldounVolume233",
     "Al-Muqaddima - Introduction à l'histoire universelle - Les prolégomènes d'Ibn Khaldoun Volume 2-3 - المقدمة_djvu.txt",
     "Ibn Khaldun", "Les Prolégomènes (Muqaddimah), Volumes II-III", "French",
     "Selection / partial", "Written by the author",
     "Introducció a la història universal d'Ibn Khaldun (1377); traducció francesa "
     "de W. M. de Slane, no l'àrab original. Volums II-III de III. Digitalització OCR.",
     "Ibn_Khaldun__Prolegomenes_Vol2-3_de_Slane_fr.txt"),
    ("logischeuntersuc01hussuoft", "logischeuntersuc01hussuoft_djvu.txt",
     "Edmund Husserl", "Logische Untersuchungen, Band I (Prolegomena zur reinen Logik)",
     "German", "Selection / partial", "Written by the author",
     "Obra fundacional de la fenomenologia; original alemany d'Edmund Husserl (1900), "
     "en domini públic. Volum I de II (Prolegòmens a la lògica pura). Digitalització "
     "OCR (tipografia romana, no gòtica).",
     "Husserl__Logische_Untersuchungen_I_de.txt"),
    ("nihongi1asto", "nihongi1asto_djvu.txt",
     "Nihongi", "Nihongi: Chronicles of Japan, Vol. I (Aston)", "English",
     "Complete work", "Recorded/compiled by others",
     "Crònica xintoista del Japó compilada per la cort imperial (720 dC); traducció "
     "anglesa de W. G. Aston (1896), no el japonès clàssic original. Volum I de II. "
     "Digitalització OCR.",
     "Nihongi__Aston_Vol1_en.txt"),
    ("nihongi2asto", "nihongi2asto_djvu.txt",
     "Nihongi", "Nihongi: Chronicles of Japan, Vol. II (Aston)", "English",
     "Complete work", "Recorded/compiled by others",
     "Crònica xintoista del Japó compilada per la cort imperial (720 dC); traducció "
     "anglesa de W. G. Aston (1896), no el japonès clàssic original. Volum II de II. "
     "Digitalització OCR.",
     "Nihongi__Aston_Vol2_en.txt"),
    ("egyptianbookofde00erne_0", "egyptianbookofde00erne_0_djvu.txt",
     "Book of the Dead", "The Egyptian Book of the Dead (Papyrus of Ani)", "English",
     "Selection / partial", "Anonymous / composite",
     "Textos funeraris de l'antic Egipte, de composició anònima i acumulats al llarg "
     "de segles; recensió del Papir d'Ani. Edició d'E. A. W. Budge (1895) amb traducció "
     "anglesa, introducció i transliteració (l'OCR inclou aquest aparat). No l'egipci original.",
     "Book_of_the_Dead__Papyrus_of_Ani_Budge_en.txt"),

    # --- Lot 7 ---
    ("in.ernet.dli.2015.65699", "2015.65699.The-Rig-Veda_djvu.txt",
     "Rig Veda", "The Rig Veda", "English",
     "Selection / partial", "Anonymous / composite",
     "Himnes vèdics de transmissió oral i autoria anònima (els textos més antics de "
     "l'hinduisme); traducció anglesa de domini públic (s. XIX), no el sànscrit "
     "original. Digitalització OCR.",
     "Rig_Veda__en.txt"),
    ("lawsofmanu00manuuoft", "lawsofmanu00manuuoft_djvu.txt",
     "Laws of Manu", "The Laws of Manu (Manusmriti, SBE vol. XXV)", "English",
     "Complete work", "Attributed (authorship debated)",
     "Tractat de dret i deure hindú (dharmaśāstra) atribuït tradicionalment a Manu; "
     "traducció de Georg Bühler (1886, SBE vol. XXV), no el sànscrit original. "
     "Digitalització OCR.",
     "Laws_of_Manu__Buhler_en.txt"),
    ("principlesofmost00conw", "principlesofmost00conw_djvu.txt",
     "Anne Conway", "The Principles of the Most Ancient and Modern Philosophy", "English",
     "Complete work", "Written by the author",
     "Tractat metafísic d'Anne Conway (escrit cap a 1677, publicat pòstumament el 1690). "
     "Anglès de l'època. Digitalització OCR.",
     "Anne_Conway__Principles_en.txt"),
    ("discursoenelcong00boli", "discursoenelcong00boli_djvu.txt",
     "Simon Bolivar", "Discurso de Angostura (1819)", "Spanish",
     "Complete work", "Written by the author",
     "Discurs de Simón Bolívar al Congrés d'Angostura (1819); edició de Caracas (1922). "
     "Digitalització OCR.",
     "Simon_Bolivar__Discurso_de_Angostura_es.txt"),
    ("ramayanofvlm00valmrich", "ramayanofvlm00valmrich_djvu.txt",
     "Ramayana", "The Ramayan of Valmiki (Griffith)", "English",
     "Complete work", "Attributed (authorship debated)",
     "Poema èpic sànscrit atribuït a Valmiki; traducció en vers de Ralph T. H. Griffith "
     "(1895), no el sànscrit original. Digitalització OCR.",
     "Ramayana__Griffith_en.txt"),
    ("TristanPeregrinations01BNF", "TristanPeregrinations01BNF_djvu.txt",
     "Flora Tristan", "Pérégrinations d'une paria, tome I", "French",
     "Selection / partial", "Written by the author",
     "Memòries i crítica social de Flora Tristan (1838), volum I. Original francès en "
     "domini públic. Digitalització OCR.",
     "Flora_Tristan__Peregrinations_I_fr.txt"),
    ("the-spirits-book-by-allan-kardec", "The Spirits Book by Allan Kardec _djvu.txt",
     "Allan Kardec", "The Spirits' Book", "English",
     "Complete work", "Written by the author",
     "Obra fundacional de l'espiritisme, d'Allan Kardec (original francès 1857); "
     "traducció anglesa de domini públic (Blackwell). Digitalització OCR.",
     "Allan_Kardec__The_Spirits_Book_en.txt"),

    # --- Lot 8 ---
    ("holyscripturesac028077mbp", "holyscripturesac028077mbp_djvu.txt",
     "Tanakh", "The Holy Scriptures according to the Masoretic Text (JPS 1917)", "English",
     "Complete work", "Anonymous / composite",
     "Bíblia hebrea (Tanakh), antologia de molts textos i autors recopilats al llarg de "
     "segles; traducció anglesa jueva de la Jewish Publication Society (1917), no l'hebreu "
     "original. Digitalització OCR.",
     "Tanakh__JPS_1917_en.txt"),
    ("taoistteachings00liehuoft", "taoistteachings00liehuoft_djvu.txt",
     "Liezi", "Taoist Teachings from the Book of Lieh-Tzu", "English",
     "Selection / partial", "Attributed (authorship debated)",
     "Clàssic taoista atribuït a Lie Zi; traducció (selecció) de Lionel Giles (1912), no "
     "el xinès original complet. Digitalització OCR.",
     "Liezi__Giles_en.txt"),
    ("wg949", "WG949-1894 -The Sacred Books of East - Vol 49 of 50 - Buddhism-Mahâyâna Texts_djvu.txt",
     "Mahayana Sutras",
     "Buddhist Mahayana Texts: Diamond Sutra, Heart Sutra, Sukhavativyuha (SBE XLIX)",
     "English", "Selection / partial", "Anonymous / composite",
     "Sutres budistes mahayana de composició anònima; inclou el Sutra del Diamant "
     "(Vajracchedika) i el Sutra del Cor; traduccions de Müller, Cowell i Takakusu (1894, "
     "SBE vol. XLIX), no el sànscrit original. Digitalització OCR.",
     "Mahayana_Sutras__SBE49_en.txt"),
    ("wg921", "WG921-1884 -The Sacred Books of East - Vol 21 of 50-Buddhism-The Saddharma- Pundarika or The Lotus of the True Law_djvu.txt",
     "Lotus Sutra", "The Saddharma-Pundarika (Lotus of the True Law, SBE XXI)", "English",
     "Complete work", "Anonymous / composite",
     "Sutra mahayana de composició anònima; traducció de Hendrik Kern (1884, SBE vol. XXI), "
     "no el sànscrit original. Digitalització OCR.",
     "Lotus_Sutra__Kern_en.txt"),
    ("wg922", "WG922-1884 -The Sacred Books of East - Vol 22 of 50 - Jain Sutras - Part 1 Of 2_djvu.txt",
     "Jaina Sutras", "Jaina Sutras, Part I: Acaranga and Kalpa Sutra (SBE XXII)", "English",
     "Selection / partial", "Anonymous / composite",
     "Escriptures jainistes (Acaranga i Kalpa Sutra) de transmissió i autoria tradicional; "
     "traducció de Hermann Jacobi (1884, SBE vol. XXII), no el prakrit original. Part I de "
     "II. Digitalització OCR.",
     "Jaina_Sutras__Jacobi_I_en.txt"),
]


def fetch(identifier: str, djvu: str) -> str | None:
    # Els noms de fitxer poden contenir espais/accents -> cal codificar-los per a la URL.
    url = (
        "https://archive.org/download/"
        + urllib.parse.quote(identifier)
        + "/"
        + urllib.parse.quote(djvu)
    )
    for attempt in range(3):  # reintents: archive.org pot fallar transitòriament
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SigPhi)"})
            with urllib.request.urlopen(req, timeout=180) as r:  # urllib segueix el 302
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"   intent {attempt + 1}/3 fallit ({identifier}): {e}")
            time.sleep(3)
    return None


def clean_ocr(text: str) -> str:
    # Si és un mirall de Project Gutenberg, treu la capçalera/peu legal.
    m = _GUT_START.search(text)
    if m:
        text = text[m.end():]
    m = _GUT_END.search(text)
    if m:
        text = text[:m.start()]
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
