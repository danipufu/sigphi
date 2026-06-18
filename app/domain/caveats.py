"""
SigPhi — Classificació de COMPLETESA i AUTORIA de cada obra.
Genera els avisos que la IA ha de comunicar a l'usuari quan un text:
  - és incomplet (fragments, selecció, part d'una obra)
  - NO va ser escrit directament per l'autor (atribuït, recollit per deixebles, anònim)
Usat per assemble_corpus.py (capçalera) i ingest.py (metadades per chunk).
"""
import re

# ── Autors dels quals NOMÉS sobreviuen fragments ───────────────────────────
FRAGMENT_AUTHORS = {
    "heraclitus", "parmenides", "empedocles", "democritus", "anaxagoras",
}

# ── Obres RECOLLIDES/COMPILADES per altres (no escrites per l'autor) ────────
RECORDED = {
    "confucius":   "The Analects were compiled by Confucius's disciples after his death, not written by him.",
    "epictetus":   "Epictetus wrote nothing himself; his teachings were recorded by his student Arrian.",
    "mencius":     "Compiled by Mencius together with his disciples.",
    "huineng":     "Recorded and compiled by disciples; traditionally attributed to Huineng.",
}

# ── Obres d'autoria TRADICIONAL/ATRIBUÏDA (debatuda) ────────────────────────
ATTRIBUTED = {
    "laozi":       "Traditional attribution to Laozi; authorship and date are debated.",
    "sunzi":       "Traditional attribution to Sun Tzu; authorship is debated.",
    "sun tzu":     "Traditional attribution to Sun Tzu; authorship is debated.",
    "bodhidharma": "Attributed to Bodhidharma; authorship is traditional and uncertain.",
    "zhuangzi":    "The Inner Chapters are attributed to Zhuangzi; the rest likely come from his school.",
}

# ── Textos ANÒNIMS / COMPOSTOS / MITOLÒGICS (per autor o per títol) ─────────
ANONYMOUS = {
    "popol vuh":        "Anonymous Maya-Quiché text, transmitted orally before being transcribed.",
    "mabinogion":       "Anonymous medieval Welsh compilation of tales.",
    "gospel of thomas": "Anonymous; pseudepigraphally attributed to the apostle Thomas.",
    "pistis sophia":    "Anonymous Gnostic text of uncertain authorship.",
    "bardo thodol":     "Terma traditionally attributed to Padmasambhava; compiled and transmitted later.",
    "tibetan book of the dead": "Terma traditionally attributed to Padmasambhava; compiled later.",
}

# ── Paraules de títol que indiquen text PARCIAL o FRAGMENTARI ──────────────
PARTIAL_TITLE  = ["selection", "selections", "abridg", "extract", "excerpt", "anthology"]
FRAGMENT_TITLE = ["fragment"]


# ── Textos amb CONTINGUT DISCRIMINATORI ─────────────────────────────────────
# Clau: (fragment_autor_norm, fragment_obra_norm); valor: avís a mostrar. El match
# (caveats.discriminatory_warning) és per SUBCADENA normalitzada: l'autor del chunk
# ha de contenir la 1a clau I l'obra la 2a (2a clau buida = qualsevol obra d'aquell
# autor). Manté la redacció mesurada: descriu el contingut + desvinculació, mai
# judici de valor sobre l'autor.
# NOTA: la revisió completa obra-per-obra requereix el catàleg en viu (títols i
# presència reals); aquí només hi ha els casos d'alta confiança. Vegeu la memòria
# sigphi-corpus-discrimination per als candidats pendents de verificar.
DISCRIMINATORY_CONTENT: dict[tuple[str, str], str] = {
    ("martin luther", "jews"): (
        "CONTINGUT DISCRIMINATORI: tractat violentament antisemita. Luter proposa "
        "cremar sinagogues i expulsar els jueus. Citat per la propaganda nazi. "
        "Repudiat per la Federació Luterana Mundial (LWF, 2015). Inclòs únicament "
        "per al seu valor historiogràfic."
    ),
    ("karl marx", "jewish question"): (
        "CONTINGUT DISCRIMINATORI: l'assaig conté estereotips antisemites sobre els "
        "jueus i els diners, típics del discurs del segle XIX. Text fundacional del "
        "pensament marxista, però amb elements de discurs antisemita."
    ),
    ("laws of manu", ""): (
        "CONTINGUT DISCRIMINATORI: codi legal-religiós que estableix la jerarquia de "
        "castes, amb nombroses disposicions que subordinen els xudres, els grups "
        "'intocables' i les dones. Text històric d'estudi; inclòs pel seu valor "
        "historiogràfic, no com a aval del seu contingut."
    ),
    ("aristotle", "politic"): (
        "CONTINGUT DISCRIMINATORI: l'obra defensa l'esclavitud 'natural' i la "
        "subordinació natural de les dones i dels 'bàrbars'. Passatges propis del seu "
        "context (s. IV aC); inclosos pel seu valor historiogràfic, no com a aval."
    ),
    # Traduccions angleses antigues de la Política titulen l'obra "A Treatise on
    # Government" (Ellis): mateix avís, títol alternatiu.
    ("aristotle", "treatise on government"): (
        "CONTINGUT DISCRIMINATORI: l'obra defensa l'esclavitud 'natural' i la "
        "subordinació natural de les dones i dels 'bàrbars'. Passatges propis del seu "
        "context (s. IV aC); inclosos pel seu valor historiogràfic, no com a aval."
    ),
}


def _norm(s):
    return re.sub(r'[_\s]+', ' ', (s or '')).strip().lower()


def _match(text, mapping):
    for key, msg in mapping.items():
        if key in text:
            return msg
    return None


def discriminatory_warning(author: str, work: str) -> str | None:
    """Retorna l'avís de contingut discriminatori si l'autor+obra hi coincideix."""
    a, w = _norm(author), _norm(work)
    for (ka, kw), msg in DISCRIMINATORY_CONTENT.items():
        if ka in a and kw in w:
            return msg
    return None


def classify(author, title):
    """Retorna (completeness, authorship, note)."""
    a, t = _norm(author), _norm(title)
    completeness = "Complete work"
    authorship = "Written by the author"
    notes = []

    # 1) AUTORIA (prioritat: recollit > atribuït > anònim)
    msg = _match(a, RECORDED)
    if msg:
        authorship = "Recorded/compiled by others"
        notes.append(msg)
    elif _match(a, ATTRIBUTED):
        authorship = "Attributed (authorship debated)"
        notes.append(_match(a, ATTRIBUTED))
    elif _match(a + " " + t, ANONYMOUS):
        authorship = "Anonymous / composite"
        notes.append(_match(a + " " + t, ANONYMOUS))

    # 2) COMPLETESA
    if any(k in a for k in FRAGMENT_AUTHORS) or any(k in t for k in FRAGMENT_TITLE):
        completeness = "Fragments only"
        notes.append("Only fragments survive, preserved as quotations by later authors; the text is incomplete.")
    elif any(k in t for k in PARTIAL_TITLE):
        completeness = "Selection / partial"
        notes.append("This is a selection or abridgement, not the complete work.")

    return completeness, authorship, (" ".join(notes) if notes else "—")
