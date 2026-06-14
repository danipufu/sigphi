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

    # --- Lot 6: diàlegs de Plató que faltaven (trad. Jowett 1871, Gutenberg) ---
    # IDs verificats un a un a la pàgina de cada ebook (l'ID "de memòria" pot
    # col·lidir: p.ex. 6762 NO és la Retòrica d'Aristòtil sinó la Política).
    (1580, "Plato", "Charmides", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre la temprança; traducció de Benjamin Jowett (1871), "
     "domini públic, no el grec original.",
     "Plato__Charmides_Jowett_en.txt"),
    (1584, "Plato", "Laches", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre el valor; traducció de Benjamin Jowett (1871), domini "
     "públic, no el grec original.",
     "Plato__Laches_Jowett_en.txt"),
    (1598, "Plato", "Euthydemus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató; traducció de Benjamin Jowett (1871), domini públic, no el "
     "grec original.",
     "Plato__Euthydemus_Jowett_en.txt"),
    (1616, "Plato", "Cratylus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre el llenguatge; traducció de Benjamin Jowett (1871), "
     "domini públic, no el grec original.",
     "Plato__Cratylus_Jowett_en.txt"),
    (1673, "Plato", "Lesser Hippias", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató (Hipies Menor); traducció de Benjamin Jowett (1871), domini "
     "públic, no el grec original.",
     "Plato__Lesser_Hippias_Jowett_en.txt"),
    (1682, "Plato", "Menexenus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató; traducció de Benjamin Jowett (1871), domini públic, no el "
     "grec original.",
     "Plato__Menexenus_Jowett_en.txt"),
    (1744, "Plato", "Philebus", "English",
     "Complete work", "Written by the author",
     "Diàleg de Plató sobre el plaer i el bé; traducció de Benjamin Jowett (1871), "
     "domini públic, no el grec original.",
     "Plato__Philebus_Jowett_en.txt"),

    # --- Lot 7: Nietzsche (Consideracions intempestives I) ---
    (51710, "Nietzsche",
     "Thoughts Out of Season, Part I (David Strauss; Richard Wagner in Bayreuth)",
     "English", "Complete work", "Written by the author",
     "Consideracions intempestives I; conté 'David Strauss, the Confessor and "
     "Writer' i 'Richard Wagner in Bayreuth'. Traducció d'A. M. Ludovici (ed. Levy), "
     "domini públic. (Wagner in Bayreuth pot duplicar una entrada existent.)",
     "Nietzsche__Thoughts_Out_of_Season_I_en.txt"),

    # --- Lot 8: anarquistes restaurats com a autors propis (curació) ---
    # Aquests textos abans estaven MAL atribuïts a Emma Goldman (els vam treure);
    # ara entren amb l'autoria correcta.
    (34406, "Alexander Berkman", "Prison Memoirs of an Anarchist", "English",
     "Complete work", "Written by the author",
     "Memòries de presó d'Alexander Berkman (1912), domini públic. Abans estava mal "
     "atribuït a Emma Goldman al corpus.",
     "Alexander_Berkman__Prison_Memoirs_en.txt"),
    (43098, "Voltairine de Cleyre", "Selected Works of Voltairine de Cleyre", "English",
     "Complete work", "Written by the author",
     "Antologia d'assaigs i poemes de Voltairine de Cleyre (ed. Berkman, 1914), "
     "domini públic. Conté 'In Defense of Emma Goldman', abans mal atribuït a Goldman.",
     "Voltairine_de_Cleyre__Selected_Works_en.txt"),

    # --- Lot 9: hadits (dites del profeta Mahoma) — selecció PD ---
    (58426, "Hadith",
     "The Speeches and Table-Talk of the Prophet Mohammad (Lane-Poole)", "English",
     "Selection / partial", "Recorded/compiled by others",
     "Selecció de les dites i discursos del profeta Mahoma (hadits), transmesos i "
     "compilats pels seguidors; edició de Stanley Lane-Poole (1882), domini públic, "
     "no l'àrab original. (Els grans reculls -Bukhari, Muslim- només tenen traducció "
     "anglesa moderna amb copyright.)",
     "Hadith__Speeches_Table_Talk_Lane_Poole_en.txt"),

    # --- Lot 10: cluster B (anarquistes/polítics, filòsofs, mística) — Gutenberg PD ---
    (360, "Proudhon",
     "What is Property? An Inquiry into the Principle of Right and of Government",
     "English", "Complete work", "Written by the author",
     "Obra clàssica de l'anarquisme de P.-J. Proudhon (1840); trad. de Benjamin Tucker, "
     "domini públic. (És l'obra a què respon la 'Misèria de la filosofia' de Marx.)",
     "Proudhon__What_is_Property_en.txt"),
    (34580, "Max Stirner", "The Ego and His Own", "English",
     "Complete work", "Written by the author",
     "Obra fundacional de l'egoisme de Max Stirner (1844); trad. de S. Byington, domini públic.",
     "Max_Stirner__The_Ego_and_His_Own_en.txt"),
    (4341, "Peter Kropotkin", "Mutual Aid: A Factor of Evolution", "English",
     "Complete work", "Written by the author",
     "Tesi de Piotr Kropotkin sobre la cooperació com a factor evolutiu (1902), domini públic.",
     "Peter_Kropotkin__Mutual_Aid_en.txt"),
    (23428, "Peter Kropotkin", "The Conquest of Bread", "English",
     "Complete work", "Written by the author",
     "Obra anarcocomunista de Piotr Kropotkin (1892), domini públic.",
     "Peter_Kropotkin__Conquest_of_Bread_en.txt"),
    (36568, "Mikhail Bakunin", "God and the State", "English",
     "Complete work", "Written by the author",
     "Assaig antiteista i anarquista de M. Bakunin (1871, pòstum); trad. anglesa, domini públic.",
     "Mikhail_Bakunin__God_and_the_State_en.txt"),
    (5827, "Bertrand Russell", "The Problems of Philosophy", "English",
     "Complete work", "Written by the author",
     "Introducció clàssica de Bertrand Russell (1912), domini públic.",
     "Bertrand_Russell__Problems_of_Philosophy_en.txt"),
    (47025, "Ludwig Feuerbach", "The Essence of Christianity", "English",
     "Complete work", "Written by the author",
     "Crítica de la religió de L. Feuerbach (1841); trad. de George Eliot (Mary Ann "
     "Evans), domini públic. (Influència clau en el jove Marx.)",
     "Ludwig_Feuerbach__Essence_of_Christianity_en.txt"),
    (1653, "Thomas a Kempis", "The Imitation of Christ", "English",
     "Complete work", "Written by the author",
     "Clàssic devocional cristià de Tomàs de Kempis (c. 1420); trad. anglesa, domini públic.",
     "Thomas_a_Kempis__Imitation_of_Christ_en.txt"),
    (4239, "Thomas Malthus", "An Essay on the Principle of Population", "English",
     "Complete work", "Written by the author",
     "Assaig de T. R. Malthus sobre població i recursos (1798), domini públic.",
     "Thomas_Malthus__Principle_of_Population_en.txt"),
    (33310, "David Ricardo", "On the Principles of Political Economy and Taxation",
     "English", "Complete work", "Written by the author",
     "Obra fonamental d'economia política de David Ricardo (1817), domini públic.",
     "David_Ricardo__Principles_Political_Economy_en.txt"),
    (246, "Omar Khayyam", "Rubaiyat of Omar Khayyam (FitzGerald)", "English",
     "Selection / partial", "Attributed (authorship debated)",
     "Quartetes perses atribuïdes a Omar Khayyam (s. XI-XII); cèlebre versió anglesa "
     "d'Edward FitzGerald (1859), domini públic, no el persa original.",
     "Omar_Khayyam__Rubaiyat_FitzGerald_en.txt"),
    (55046, "Herbert Spencer", "First Principles", "English",
     "Complete work", "Written by the author",
     "Obra fonamental del sistema filosòfic evolucionista de Herbert Spencer (1862), "
     "domini públic.",
     "Herbert_Spencer__First_Principles_en.txt"),
    (45159, "Rumi", "The Persian Mystics: Jalalu'd-din Rumi", "English",
     "Selection / partial", "Written by the author",
     "Selecció de la mística sufí de Jalal-ad-Din Rumi (s. XIII); versió anglesa de "
     "F. Hadland Davis (Wisdom of the East, 1907), domini públic, no el persa original.",
     "Rumi__Persian_Mystics_en.txt"),
    (33742, "Jacob Boehme", "Dialogues on the Supersensual Life", "English",
     "Selection / partial", "Written by the author",
     "Diàlegs místics de Jakob Böhme (s. XVII); traducció anglesa de domini públic.",
     "Jacob_Boehme__Supersensual_Life_en.txt"),
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
    # Soroll editorial: crèdit "Produced by ..." del principi (només 1a aparició).
    text = re.sub(r"(?is)\A\s*Produced by .*?\n\s*\n", "", text, count=1)
    return text.strip()


def strip_jowett_intro(text: str) -> str:
    """Diàlegs de Plató (Jowett): talla la llarga INTRODUCTION/ANALYSIS del traductor
    i comença al diàleg pròpiament dit. Marcador fiable: la capçalera en MAJÚSCULES
    'PERSONS OF THE DIALOGUE'. Si no hi és, no toca res (zero risc de retallar el text)."""
    m = re.search(r"(?m)^PERSONS OF THE DIALOGUE", text)
    if m:
        return text[m.start():].strip()
    return text


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
        if author == "Plato":  # treu la introducció del traductor (Jowett)
            body = strip_jowett_intro(body)
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
