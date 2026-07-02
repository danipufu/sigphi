"""Verificador determinista de cites: pur codi, cap crida a LLM.

Comprova que cada cita "(Autor, Obra[, Localitzador])" que apareix al text de
la resposta (format de la regla 2 del SYSTEM_PROMPT) correspon REALMENT a una
font que s'ha recuperat per a aquesta pregunta. Protegeix la promesa central
de SigPhi ("tota cita és verificable") contra el pitjor error possible: una
cita fabricada que el model s'hagi inventat.

NOMÉS detecta i informa (log + camp a ChatResult/eval); no reescriu ni talla
la resposta — la matisació heurística (què compta com "prou semblant") no és
prou fiable per editar el text de l'usuari automàticament sense risc de fals
positiu, però sí prou fiable per a observabilitat i revisió.
"""
from __future__ import annotations
import re
import unicodedata

from app.domain.models import Citation, RetrievedChunk

# Cita: parèntesi amb com a mínim una coma (Autor, Obra); pot haver-n'hi
# diverses dins el mateix parèntesi separades per ";".
_PAREN_RE = re.compile(r"\(([^()]{4,220})\)")

# Partícules habituals en noms d'autor que no cal que vagin en majúscula
# ("Thomas a Kempis", "Ibn al-Haytham", "Lao Tzu i Chuang Tzu"...).
_NAME_PARTICLES = {
    "de", "van", "von", "der", "den", "al", "el", "ibn", "da", "le", "la",
    "of", "the", "i", "y", "and", "a",
}


def _norm(s: str) -> str:
    """Normalitza per a comparació fluixa: sense accents, minúscules, sense
    puntuació, espais compactats."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _looks_like_author_segment(seg: str) -> bool:
    """Filtre per descartar incisos de prosa normal ("that is, ...", "i.e.,
    ...") que tenen coma però NO són una cita: exigeix que sembli un nom propi
    (paraules capitalitzades, curt), no una clàusula."""
    words = seg.split()
    if not words or len(words) > 6:
        return False
    if not words[0][0].isupper():
        return False
    for w in words[1:]:
        w_clean = w.strip(".,-'’")
        if not w_clean or w_clean.lower() in _NAME_PARTICLES:
            continue
        if not (w_clean[0].isupper() or w_clean[0].isdigit()):
            return False
    return True


def extract_citations(answer: str) -> list[Citation]:
    """Extreu totes les cites "(Autor, Obra[, Localitzador])" del text, tal
    com el model les ha escrit (sense normalitzar)."""
    out: list[Citation] = []
    for m in _PAREN_RE.finditer(answer):
        for part in m.group(1).split(";"):
            part = part.strip()
            if "," not in part:
                continue
            segs = [s.strip() for s in part.split(",")]
            if len(segs) < 2 or not segs[0] or not segs[1]:
                continue
            if not _looks_like_author_segment(segs[0]):
                continue
            section = ", ".join(s for s in segs[2:] if s) or None
            out.append(Citation(author=segs[0], work=segs[1], section=section))
    return out


def unverified_citations(answer: str, retrieved: list[RetrievedChunk]) -> list[Citation]:
    """Retorna les cites del text que NO corresponen a cap font realment
    recuperada (ni per autor ni per obra, amb marge per a variants menors de
    títol). Llista buida si totes verifiquen contra `retrieved`."""
    known_authors = {_norm(r.chunk.author) for r in retrieved if r.chunk.author}
    known_pairs = {
        (_norm(r.chunk.author), _norm(r.chunk.work)) for r in retrieved if r.chunk.author
    }
    bad: list[Citation] = []
    for c in extract_citations(answer):
        na, nw = _norm(c.author), _norm(c.work)
        if not na or na not in known_authors:
            bad.append(c)
            continue
        # Obra: coincidència exacta, o una és subcadena de l'altra (el model
        # sovint escurça o amplia lleugerament el títol; és legítim).
        if not any(a == na and (w == nw or w in nw or nw in w) for a, w in known_pairs):
            bad.append(c)
    return bad
