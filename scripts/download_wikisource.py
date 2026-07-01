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
    # Reemplaça els "Epistles EN/LA" de Perseus (llatí amb aparat / Hipòcrates).
    # Wikisource té la traducció anglesa neta de Gummere, en 124 subpàgines
    # "Letter N" (índex amb TOC llarg -> cal el llindar >=5 subpàgines de collect).
    ("en", "Moral letters to Lucilius",
     "Seneca", "Moral Letters to Lucilius (Epistulae Morales)", "English",
     "Complete work", "Written by the author",
     "Les 124 Epistulae Morales ad Lucilium de Sèneca sobre ètica estoica; "
     "traducció anglesa de Richard M. Gummere (Loeb, 1917-25), domini públic. "
     "Text de Wikisource.",
     "Seneca__Moral_Letters_to_Lucilius_en.txt"),
    ("en", "The Great Encyclical Letters of Pope Leo XIII",
     "Leo XIII",
     "Great Encyclical Letters (incl. Aeterni Patris, Providentissimus Deus, etc.)",
     "English", "Complete work", "Written by the author",
     "Col·lecció de 30 encíclics de Lleó XIII (1878-1903), ed. Benziger Brothers (1903), PD; "
     "inclou: Aeterni Patris (1879, restauració de la filosofia tomista), "
     "Providentissimus Deus (1893, estudis bíblics), Divinum Illud Munus (1897, Esperit Sant), "
     "Satis Cognitum (1896, unitat de l'Església) i 26 encíclics més sobre política, "
     "família i doctrina social. Text de Wikisource.",
     "Leo_XIII__Great_Encyclical_Letters_en.txt"),

    # === Juan de la Cruz ===
    ("es", "Noche oscura del alma",
     "Juan de la Cruz", "Noche oscura del alma", "Spanish",
     "Complete work", "Written by the author",
     "Poema i comentari en prosa de Juan de la Cruz (c. 1578-1584) sobre el camí de "
     "purificació mística de l'ànima cap a la unió amb Déu. Text de Wikisource.",
     "Juan_de_la_Cruz__Noche_oscura_del_alma_es.txt"),
    ("es", "Cántico espiritual",
     "Juan de la Cruz", "Cántico espiritual", "Spanish",
     "Complete work", "Written by the author",
     "Poema místic i comentari en prosa de Juan de la Cruz (c. 1578), al·legoritzant "
     "la recerca de l'ànima per l'Estimat; inspirat en el Càntic dels Càntics. "
     "Text de Wikisource.",
     "Juan_de_la_Cruz__Cantico_espiritual_es.txt"),

    # === Ramon Llull — obres en català de Wikisource ===
    ("ca", "Libre del gentil e los tres savis",
     "Ramon Llull", "Libre del gentil e los tres savis", "Catalan",
     "Complete work", "Written by the author",
     "Diàleg apologètic de Ramon Llull (c. 1274-1276) en el qual un gentil debat amb "
     "tres savis de les tres religions abrahamiques. Català medieval. Text de Wikisource.",
     "Llull__Libre_del_gentil_ca.txt"),
    ("ca", "Libre de mil proverbis",
     "Ramon Llull", "Libre de mil proverbis", "Catalan",
     "Complete work", "Written by the author",
     "Col·lecció de mil proverbis morals i filosòfics de Ramon Llull (1302). "
     "Català medieval. Text de Wikisource.",
     "Llull__Libre_de_mil_proverbis_ca.txt"),
    ("ca", "Libre de la primera e segona intencio",
     "Ramon Llull", "Libre de la primera e segona intenció", "Catalan",
     "Complete work", "Written by the author",
     "Tractat filosòfic de Ramon Llull sobre la primera intenció (amor a Déu) i la "
     "segona intenció (bens creats), central en la seva Ars. Català medieval. "
     "Text de Wikisource.",
     "Llull__Libre_de_la_primera_intencio_ca.txt"),
    ("ca", "Llibre d'amic e amat",
     "Ramon Llull", "Llibre d'amic e amat", "Catalan",
     "Complete work", "Written by the author",
     "Apèndix del Blanquerna de Ramon Llull (c. 1283): 366 versicles poètics sobre "
     "l'amic (l'ànima) i l'Amat (Déu). Joia de la literatura mística catalana medieval. "
     "Text de Wikisource.",
     "Llull__Llibre_d_amic_e_amat_ca.txt"),

    # === Rousseau — originals en francès ===
    ("fr", "Du contrat social",
     "Rousseau", "Du contrat social (Le contrat social)", "French",
     "Complete work", "Written by the author",
     "Tractat de filosofia política de Jean-Jacques Rousseau (1762) que formula la "
     "teoria de la sobirania popular i el contracte social. Text de Wikisource.",
     "Rousseau__Du_contrat_social_fr.txt"),
    ("fr", "Discours sur l'origine et les fondements de l'inégalité parmi les hommes",
     "Rousseau",
     "Discours sur l'origine et les fondements de l'inégalité parmi les hommes",
     "French", "Complete work", "Written by the author",
     "Segon Discurs de Rousseau (1755): critica la propietat privada i la civilització "
     "com a origen de la desigualtat humana. Text de Wikisource.",
     "Rousseau__Discours_sur_l_inegalite_fr.txt"),
    ("fr", "Discours sur les sciences et les arts",
     "Rousseau", "Discours sur les sciences et les arts", "French",
     "Complete work", "Written by the author",
     "Primer Discurs de Rousseau (1750), premiat per l'Acadèmia de Dijon: argumenta "
     "que el progrés de les ciències i les arts ha corromput els costums. "
     "Text de Wikisource.",
     "Rousseau__Discours_sur_les_sciences_fr.txt"),

    # === Bernat Metge ===
    ("ca", "Lo somni",
     "Bernat Metge", "Lo somni (El somni)", "Catalan",
     "Complete work", "Written by the author",
     "Diàleg humanista de Bernat Metge (1399) en el qual apareix l'ànima del rei "
     "Joan I i debaten sobre l'immortalitat de l'ànima, l'amor i la condició "
     "humana. Obra fundacional de la prosa catalana renaixentista. Text de Wikisource.",
     "Bernat_Metge__Lo_somni_ca.txt"),

    # === Ausiàs March ===
    ("ca", "Obras del poeta valenciá Ausias March",
     "Ausiàs March", "Poesia completa (Obras del poeta valencià Ausiàs March)", "Catalan",
     "Complete work", "Written by the author",
     "Corpus poètic complet d'Ausiàs March (c. 1400-1459), cavaller i poeta "
     "valencià, mestre de la lírica catalana medieval. Poesia amorosa, moral i de "
     "mort en llengua valenciana medieval. Text de Wikisource.",
     "Ausias_March__Poesia_ca.txt"),

    # === Anselm de Canterbury ===
    ("fr", "Proslogion",
     "Anselm of Canterbury", "Proslogion (Discours sur l'existence de Dieu)", "French",
     "Complete work", "Written by the author",
     "Tractat d'Anselm de Canterbury (1077-1078) que formula l'argument ontològic "
     "per a l'existència de Déu ('allò que no es pot concebre com a major'). "
     "Traducció francesa de domini públic. Text de Wikisource.",
     "Anselm__Proslogion_fr.txt"),

    # === Giambattista Vico — La scienza nuova (3 volums, italià) ===
    ("it", "La scienza nuova - Volume I",
     "Giambattista Vico", "La scienza nuova — Volume I", "Italian",
     "Complete work", "Written by the author",
     "Primer volum de la Scienza Nuova de Giambattista Vico (3a ed., 1744): "
     "la teoria dels tres cicles de la civilització (dels déus, dels herois i dels "
     "homes) i els principis de la ciència nova de la història. Original italià. "
     "Text de Wikisource.",
     "Vico__Scienza_nuova_I_it.txt"),
    ("it", "La scienza nuova - Volume II",
     "Giambattista Vico", "La scienza nuova — Volume II", "Italian",
     "Complete work", "Written by the author",
     "Segon volum de la Scienza Nuova de Giambattista Vico (3a ed., 1744). "
     "Original italià. Text de Wikisource.",
     "Vico__Scienza_nuova_II_it.txt"),
    ("it", "La scienza nuova - Volume III",
     "Giambattista Vico", "La scienza nuova — Volume III", "Italian",
     "Complete work", "Written by the author",
     "Tercer volum de la Scienza Nuova de Giambattista Vico (3a ed., 1744): "
     "conclou la teoria del corsi e ricorsi i aplica els principis al dret romà. "
     "Original italià. Text de Wikisource.",
     "Vico__Scienza_nuova_III_it.txt"),

    # === Georges Sorel ===
    ("fr", "Réflexions sur la violence",
     "Georges Sorel", "Réflexions sur la violence", "French",
     "Complete work", "Written by the author",
     "Obra principal de Georges Sorel (1908): teoria sindicalista revolucionària que "
     "defensa el paper energitzador del mite de la vaga general i la violència com a "
     "força moral de les classes treballadores. Text de Wikisource.",
     "Sorel__Reflexions_sur_la_violence_fr.txt"),

    # === Condorcet ===
    ("fr", "Esquisse d'un tableau historique des progrès de l'esprit humain",
     "Condorcet", "Esquisse d'un tableau historique des progrès de l'esprit humain",
     "French",
     "Complete work", "Written by the author",
     "Esbós d'un quadre històric dels progressos de l'esperit humà (1795, pòstum) de "
     "Condorcet: teoria del progrés indefinit de la humanitat a través de la raó i "
     "la ciència, redactada mentre l'autor era amagat durant el Terror revolucionari. "
     "Text de Wikisource.",
     "Condorcet__Esquisse_progres_esprit_humain_fr.txt"),

    # === Aristòtil: De Anima (reemplaça la versió Perseus que contenia els Ocells
    # d'Aristòfanes). Traducció anglesa de Charles Collier (1855), domini públic.
    # Wikisource conté els 3 llibres complets en subpàgines Book_1/Chapter_N etc. ===
    ("en", "On the Vital Principle",
     "Aristotle", "De Anima (On the Soul)", "English",
     "Complete work", "Written by the author",
     "De Anima (Sobre l'ànima) d'Aristòtil: els tres llibres sobre les facultats "
     "vegetativa, sensitiva i intel·lectiva de l'ànima; traducció anglesa de Charles "
     "Collier (1855), domini públic. Substitueix un fitxer Perseus corrupte. "
     "Text de Wikisource.",
     "Aristotle__De_Anima_en.txt"),

    # === Aristòtil: parts de l'Organon que faltaven (teníem Categories + Posterior
    # Analytics; l'antic "Organon_en" era només la pàgina-índex, treta per
    # remove_stubs.sh). Traducció d'Octavius F. Owen (1853, Bohn), domini públic.
    # Wikisource les té en subpàgines (Prior Analytics/Book_1-2, Topics/Book_1-8);
    # collect() les segueix. strip_mediawiki_markup neteja el marcatge a la ingesta. ===
    # Prior Analytics té només 2 subpàgines (Book 1/2) -> collect() NO les segueix
    # (llindar >=5); cal afegir-les explícitament o queda un stub de 5KB.
    ("en", "Organon (Owen)/Prior Analytics/Book 1",
     "Aristotle", "Prior Analytics, Book 1 (Organon)", "English",
     "Complete work", "Written by the author",
     "Primers Analítics d'Aristòtil, llibre I: la teoria del sil·logisme i les figures "
     "de la deducció vàlida; traducció anglesa d'Octavius F. Owen (1853), domini "
     "públic. Text de Wikisource.",
     "Aristotle__Prior_Analytics_Book1_Owen_en.txt"),
    ("en", "Organon (Owen)/Prior Analytics/Book 2",
     "Aristotle", "Prior Analytics, Book 2 (Organon)", "English",
     "Complete work", "Written by the author",
     "Primers Analítics d'Aristòtil, llibre II: propietats dels sil·logismes, inducció "
     "i exemples; traducció anglesa d'Octavius F. Owen (1853), domini públic. "
     "Text de Wikisource.",
     "Aristotle__Prior_Analytics_Book2_Owen_en.txt"),
    ("en", "Organon (Owen)/On Interpretation",
     "Aristotle", "On Interpretation (Organon)", "English",
     "Complete work", "Written by the author",
     "Sobre la interpretació (De Interpretatione) d'Aristòtil: proposicions, judici i "
     "modalitat; traducció anglesa d'Octavius F. Owen (1853), domini públic. "
     "Text de Wikisource.",
     "Aristotle__On_Interpretation_Owen_en.txt"),
    ("en", "Organon (Owen)/Topics",
     "Aristotle", "Topics (Organon)", "English",
     "Complete work", "Written by the author",
     "Tòpics d'Aristòtil: el raonament dialèctic a partir d'opinions plausibles (vuit "
     "llibres); traducció anglesa d'Octavius F. Owen (1853), domini públic. "
     "Text de Wikisource.",
     "Aristotle__Topics_Owen_en.txt"),
    ("en", "Organon (Owen)/The Sophistical Elenchi",
     "Aristotle", "Sophistical Refutations (Organon)", "English",
     "Complete work", "Written by the author",
     "Refutacions sofístiques (De Sophisticis Elenchis) d'Aristòtil: el tractament de "
     "les fal·làcies lògiques; traducció anglesa d'Octavius F. Owen (1853), domini "
     "públic. Text de Wikisource.",
     "Aristotle__Sophistical_Refutations_Owen_en.txt"),

    # --- Lot 29: Bakunin en rus original (cap traducció anglesa segura en PD) ---
    ("ru", "Государственность и анархия (Бакунин)",
     "Mikhail Bakunin", "Государственность и анархия (Statism and Anarchy)", "Russian",
     "Selection / partial", "Written by the author",
     "Obra major de Bakunin (1873) sobre l'estat, el marxisme autoritari i "
     "l'anarquisme; escrita originalment en rus (sense problema de traductor: "
     "Bakunin †1876, domini públic). La transcripció de Wikisource és parcial "
     "(talla a mig text) però substancial (~25.000 paraules). Text de Wikisource.",
     "Bakunin__Gosudarstvennost_i_anarkhiya_ru.txt"),

    # --- Lot 30: francès original (la trad. anglesa Robinson 1923 és de préstec restringit) ---
    ("fr", "Idée générale de la Révolution au dix-neuvième siècle/Texte entier",
     "Proudhon", "Idée générale de la Révolution au dix-neuvième siècle", "French",
     "Complete work", "Written by the author",
     "Manifest de Proudhon (1851) a favor del federalisme mutualista i contra "
     "l'estat centralitzat; obra fundacional de l'anarquisme. Francès original "
     "(la traducció anglesa de John Beverly Robinson, 1923, PD, només es troba "
     "en préstec restringit a Internet Archive). Text de Wikisource.",
     "Proudhon__Idee_generale_de_la_Revolution_fr.txt"),
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
    # És índex (cal seguir subpàgines) si: hi ha subpàgines I (la pàgina té poc
    # text propi O hi ha molts enllaços de subpàgina). El segon cas cobreix índexs
    # amb un TOC llarg però que NO contenen l'obra (ex. "Moral letters to
    # Lucilius" -> 124 subpàgines "Letter N"); el llindar >=5 evita seguir enllaços
    # incidentals d'una obra que ja és completa en una sola pàgina.
    is_index = bool(subs) and (len(text) < MIN_FULL or len(subs) >= 5)
    if not is_index:
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
