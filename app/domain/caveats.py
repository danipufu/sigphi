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
# Cada regla: clau (autor_substr, obra_substr) -> valor (avís, triggers).
# El match d'autor/obra és per SUBCADENA normalitzada (obra_substr = "" -> qualsevol
# obra d'aquell autor; útil quan l'assaig viu dins una col·lecció gran i el trigger
# el localitza).
#   triggers = None  -> NIVELL D'OBRA: avisa a QUALSEVOL chunk de l'obra. Per a textos
#                       on la discriminació és pervasiva/definitòria de tot el text.
#   triggers = (...) -> NIVELL DE PASSATGE: només avisa si el TEXT del chunk conté
#                       alguna de les frases (normalitzades). Evita sobre-avisar quan
#                       la part discriminatòria és només un capítol/assaig dins una
#                       obra gran (p. ex. l'esclavitud és al Llibre I de la Política).
#                       COMPROMÍS: més precís, però si la traducció del corpus difereix
#                       de les frases pot deixar d'avisar; per això s'hi posen diverses
#                       variants. Si cap casa, NO avisa.
# Redacció mesurada: descriu el contingut + desvinculació; en casos DEBATUTS (Marx)
# es nota el debat en comptes d'emetre un veredicte.
DISCRIMINATORY_CONTENT: dict[tuple[str, str], tuple[str, tuple[str, ...] | None]] = {
    # — Nivell d'obra (discriminació pervasiva/definitòria) —
    ("martin luther", "jews"): (
        "CONTINGUT DISCRIMINATORI: tractat violentament antisemita. Luter proposa "
        "cremar sinagogues i expulsar els jueus. Citat per la propaganda nazi. "
        "Repudiat per la Federació Luterana Mundial (LWF, 2015). Inclòs únicament "
        "per al seu valor historiogràfic.",
        None,
    ),
    ("laws of manu", ""): (
        "CONTINGUT DISCRIMINATORI: codi legal-religiós que estableix la jerarquia de "
        "castes, amb nombroses disposicions que subordinen els xudres, els grups "
        "'intocables' i les dones. Text històric d'estudi; inclòs pel seu valor "
        "historiogràfic, no com a aval del seu contingut.",
        None,
    ),
    ("voltaire", "philosophical dictionary"): (
        "CONTINGUT DISCRIMINATORI: el Diccionari conté entrades —notablement l'article "
        "'Dels jueus' (Juifs)— amb estereotips i passatges antijueus, a més de polèmica "
        "despectiva contra altres grups religiosos, propis de la controvèrsia del s. "
        "XVIII. Inclòs pel seu valor historiogràfic, no com a aval.",
        None,  # obra multi-tema; frases-disparador fiables encara per verificar
    ),
    # — Nivell de passatge (la discriminació és un capítol/assaig localitzat) —
    # Aristòtil: l'esclavitud 'natural' i la subordinació de les dones són al Llibre I
    # (no a tota la Política). Frases d'Ellis ("Politics A Treatise on Government") i
    # Rackham ("Politics EN").
    ("aristotle", "politic"): (
        "CONTINGUT DISCRIMINATORI: el Llibre I defensa l'esclavitud 'natural' i la "
        "subordinació natural de les dones i dels 'bàrbars'. Passatge propi del seu "
        "context (s. IV aC); inclòs pel seu valor historiogràfic, no com a aval.",
        ("slave by nature", "slaves by nature", "by nature a slave", "natural slave",
         "intended by nature to be a slave", "the male is by nature"),
    ),
    ("aristotle", "treatise on government"): (
        "CONTINGUT DISCRIMINATORI: el Llibre I defensa l'esclavitud 'natural' i la "
        "subordinació natural de les dones i dels 'bàrbars'. Passatge propi del seu "
        "context (s. IV aC); inclòs pel seu valor historiogràfic, no com a aval.",
        ("slave by nature", "slaves by nature", "by nature a slave", "natural slave",
         "intended by nature to be a slave", "the male is by nature"),
    ),
    # Marx: els estereotips són a la 2a part. obra_substr="" perquè el mateix text
    # viu tant a "On the Jewish Question" com a "Selected Essays by Karl Marx"; els
    # disparadors són tots específics del judaisme (no falsegen en altres obres seves).
    # Cobreix dues traduccions ("secular cult"/"worldly religion of the Jew"). Cas
    # DEBATUT -> la redacció nota el debat en comptes d'emetre un veredicte.
    ("karl marx", ""): (
        "CONTINGUT DISCRIMINATORI: en aquesta part l'assaig identifica el judaisme amb "
        "els diners, l'egoisme i el comerç fent servir el vocabulari i els estereotips "
        "antijueus corrents al s. XIX ('els diners són el déu gelós d'Israel'). La "
        "lectura n'és debatuda: molts especialistes hi veuen 'judaisme' com a metàfora "
        "del capitalisme i la societat burgesa —no un atac als jueus com a poble— "
        "(Marx era d'ascendència jueva i la 1a part del text defensa l'emancipació "
        "civil dels jueus). Cal contextualitzar, no avalar.",
        ("cult of the jew", "religion of the jew", "secular basis of judaism",
         "jealous god of israel", "chimerical nationality of the jew",
         "emancipation of society from judaism", "emancipation of mankind from judaism"),
    ),
    # Hume: nota racista a l'assaig 'Of National Characters' (dins les seves col·leccions).
    ("david hume", ""): (
        "CONTINGUT DISCRIMINATORI: en una nota de l'assaig 'Of National Characters', "
        "Hume hi afirma la inferioritat 'natural' dels negres respecte als blancs. "
        "Afirmació racista pròpia del s. XVIII; inclosa pel seu valor historiogràfic, "
        "no com a aval.",
        ("apt to suspect the negroes", "naturally inferior to the whites",
         "no ingenious manufactures amongst them"),
    ),
    # Kant: afirmacions racistes sobre els africans a les 'Beobachtungen' (alemany).
    ("kant", ""): (
        "CONTINGUT DISCRIMINATORI: en aquesta obra primerenca (Beobachtungen) Kant fa "
        "afirmacions racistes sobre els africans. Passatge propi del s. XVIII; inclòs "
        "pel seu valor historiogràfic, no com a aval.",
        ("negers von afrika", "neger von afrika", "ganz schwarz, ein deutlicher beweis"),
    ),
    # Schopenhauer: assaig 'On Women' (dins 'Essays'/'Studies in Pessimism'…). Frase
    # principal verificada al corpus: "the fundamental fault in the character of women
    # is that they have no 'sense of justice'". S'eviten frases amb cometes internes
    # (la normalització no les treu i trencarien el match per subcadena).
    ("schopenhauer", ""): (
        "CONTINGUT DISCRIMINATORI: l'assaig 'Sobre les dones' (On Women) sosté la "
        "inferioritat de les dones. Misogínia pròpia del s. XIX; inclosa pel seu valor "
        "historiogràfic, no com a aval.",
        ("fault in the character of women", "want of sense of justice",
         "guilty of perjury", "big children", "the unaesthetic sex"),
    ),
}


# ── Textos amb NOTA DE CONTEXT històric/ideològic (NO discriminació de grup) ──
# Per a fonts primàries que són apologètica directa d'un règim/ideologia responsable
# de greus danys, on convé contextualitzar (no avalar) SENSE l'avís dur de
# discriminació de la regla 17. Mateixa estructura i semàntica que
# DISCRIMINATORY_CONTENT (triggers None = nivell d'obra; (...) = nivell de passatge).
HISTORICAL_CONTEXT: dict[tuple[str, str], tuple[str, tuple[str, ...] | None]] = {
    # Gentile: textos fundacionals/apologètics del feixisme. NO porten avís de
    # discriminació (no ataquen un grup; la Dottrina és de 1932, abans de les lleis
    # racials de 1938, a les quals Gentile s'oposà), però es contextualitzen.
    ("gentile", "dottrina del fascismo"): (
        "NOTA DE CONTEXT: text fundacional de la doctrina feixista, apologètica del "
        "règim de Mussolini. Inclòs pel seu valor historiogràfic, no com a aval.",
        None,
    ),
    ("gentile", "manifesto degli intellettuali fascisti"): (
        "NOTA DE CONTEXT: manifest d'adhesió al feixisme italià (1925). Inclòs pel seu "
        "valor historiogràfic, no com a aval.",
        None,
    ),
}


def _norm(s):
    return re.sub(r'[_\s]+', ' ', (s or '')).strip().lower()


def _match(text, mapping):
    for key, msg in mapping.items():
        if key in text:
            return msg
    return None


def discriminatory_warning(author: str, work: str, text: str = "") -> str | None:
    """Retorna l'avís de contingut discriminatori si escau.

    Per a regles a NIVELL D'OBRA (triggers=None) n'hi ha prou que l'autor+obra hi
    coincideixin. Per a regles a NIVELL DE PASSATGE (triggers=(...)) cal, a més, que
    el TEXT del chunk contingui alguna frase-disparador (així l'avís només surt quan
    el fragment recuperat conté realment el passatge discriminatori, no a tota l'obra).
    """
    a, w, t = _norm(author), _norm(work), _norm(text)
    for (ka, kw), (msg, triggers) in DISCRIMINATORY_CONTENT.items():
        if ka in a and kw in w:
            if triggers is None:
                return msg
            if any(trig in t for trig in triggers):
                return msg
    return None


def historical_context_note(author: str, work: str, text: str = "") -> str | None:
    """Nota de context històric/ideològic (p. ex. apologètica feixista). Categoria
    més lleugera que discriminatory_warning: contextualitza sense alarma de grup.
    Mateixa mecànica (obra/passatge)."""
    a, w, t = _norm(author), _norm(work), _norm(text)
    for (ka, kw), (msg, triggers) in HISTORICAL_CONTEXT.items():
        if ka in a and kw in w:
            if triggers is None:
                return msg
            if any(trig in t for trig in triggers):
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
