"""Verificador de SALUT del corpus indexat (ChunkStore + catàleg). Quota-free: no
fa cap crida a l'LLM. Detecta automàticament els problemes de qualitat que fins ara
es trobaven a mà:

  1. BROSSA D'OCR  — chunks il·legibles (símbols/fragments curts en lloc de prosa),
     com els 948 chunks de "Creative evolution" trobats el jun-2026.
  2. DUPLICATS     — obres del mateix autor amb títol quasi idèntic (mateixa obra
     ingerida dues vegades; difereixen en majúscules, puntuació o un sufix).
  3. OBRES TÍSIQUES — obres amb molt pocs chunks (stubs, índexs, fragments trencats).

Pensat per executar-se periòdicament i com a porta de qualitat després de cada
ingesta (CI lleuger). Surt amb codi !=0 si troba problemes (per a automatització).

Ús (al VPS, dins venv, des de l'arrel):
    VECTOR_DB_TYPE=qdrant python scripts/corpus_health.py
    VECTOR_DB_TYPE=qdrant python scripts/corpus_health.py --garbage-threshold 0.5 --min-chunks 3
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# --- Heurística de "prosa vs brossa" (pura, testable, language-agnostic) ----------

_WORD_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)  # paraula = 3+ lletres (qualsevol idioma)
_TOKEN_RE = re.compile(r"\S+")


def clean_word_ratio(text: str) -> float:
    """Fracció de 'paraules netes' (3+ lletres seguides) sobre el total de chunks de
    text separats per espais. La prosa real (en qualsevol idioma de l'alfabet llatí,
    grec, etc.) en té molta (>0.6); la brossa d'OCR, dominada per fragments curts i
    símbols ('ae LD) ate | tees AR Lt)'), molt poca (<0.4). 1.0 = text buit (no penalitza)."""
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return 1.0
    good = sum(1 for t in tokens if _WORD_RE.fullmatch(t))
    return good / len(tokens)


def looks_like_garbage(text: str, threshold: float = 0.5) -> bool:
    """True si el text sembla brossa d'OCR (poca prosa real)."""
    return clean_word_ratio(text) < threshold


# --- Detecció de SOROLL DE MARCATGE / boilerplate ---------------------------------
# clean_word_ratio NO el caça: el cos pot ser prosa neta amb marcatge incrustat
# (p. ex. el Cato llatí de Wikisource amb __NOTOC__ / "= I ="), o residus de Gutenberg.

_MARKUP_MARKERS = (
    "__NOTOC__", "__TOC__", "{|", "|}", "{{", "}}", "[[", "]]", "<ref",
    "*** START OF", "*** END OF", "Project Gutenberg", "Produced by ",
)
_HTML_ENTITY_RE = re.compile(r"&(?:amp|lt|gt|quot|nbsp|#\d+);")


def find_markup(text: str) -> list[str]:
    """Marcadors de marcatge/boilerplate residual que no s'haurien d'haver colat al
    cos del text. Retorna la llista de marcadors trobats (buida = net)."""
    found = [m for m in _MARKUP_MARKERS if m in text]
    if len(_HTML_ENTITY_RE.findall(text)) >= 3:  # entitats HTML sense descodificar
        found.append("HTML-entities")
    return found


# --- Detecció de duplicats per títol (mateix autor) -------------------------------

def _norm_title(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_duplicate_titles(works: list[str]) -> list[tuple[str, str]]:
    """Parelles d'obres del mateix autor amb títol quasi idèntic: un títol normalitzat
    és igual a l'altre o n'és prefix (>=12 car.). NO marca volums (Vol. I/II) perquè el
    número els fa divergir aviat. Retorna (a, b) candidats a duplicat."""
    pairs: list[tuple[str, str]] = []
    norm = [(_norm_title(w), w) for w in works]
    for i in range(len(norm)):
        for j in range(i + 1, len(norm)):
            n1, w1 = norm[i]
            n2, w2 = norm[j]
            if not n1 or not n2:
                continue
            short, long_ = (n1, n2) if len(n1) <= len(n2) else (n2, n1)
            if len(short) >= 12 and long_.startswith(short):
                pairs.append((w1, w2))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="Verificador de salut del corpus")
    ap.add_argument("--garbage-threshold", type=float, default=0.5)
    ap.add_argument("--min-chunks", type=int, default=3, help="obres amb menys chunks = sospitoses")
    ap.add_argument("--sample", type=int, default=3, help="chunks per obra a inspeccionar")
    args = ap.parse_args()

    from app.config import get_settings
    from app.infrastructure.chunk_store import ChunkStore

    cs = ChunkStore(get_settings().chunk_store_path)
    catalog = cs.catalog()  # [{author, works:[...]}, ...]

    garbage: list[tuple[str, str, float]] = []
    tiny: list[tuple[str, str, int]] = []
    dups: list[tuple[str, str, str]] = []
    markup: list[tuple[str, str, list[str]]] = []

    for entry in catalog:
        author = entry["author"]
        for w1, w2 in find_duplicate_titles(entry["works"]):
            dups.append((author, w1, w2))
        for work in entry["works"]:
            ids = cs.chunk_ids_of(author, work)
            if len(ids) < args.min_chunks:
                tiny.append((author, work, len(ids)))
            samples = cs.sample(author, work, args.sample)
            if samples:
                ratio = sum(clean_word_ratio(s) for s in samples) / len(samples)
                if ratio < args.garbage_threshold:
                    garbage.append((author, work, ratio))
                marks = sorted({m for s in samples for m in find_markup(s)})
                if marks:
                    markup.append((author, work, marks))
    cs.close()

    print(f"=== SALUT DEL CORPUS ===  autors={len(catalog)} obres={sum(len(e['works']) for e in catalog)}\n")
    print(f"## BROSSA D'OCR sospitosa ({len(garbage)}):")
    for a, w, r in sorted(garbage, key=lambda x: x[2]):
        print(f"  [{r:.2f}] {a} — {w}")
    print(f"\n## OBRES TÍSIQUES (<{args.min_chunks} chunks) ({len(tiny)}):")
    for a, w, n in sorted(tiny, key=lambda x: x[2]):
        print(f"  [{n} chunks] {a} — {w}")
    print(f"\n## SOROLL DE MARCATGE / boilerplate ({len(markup)}):")
    for a, w, marks in markup:
        print(f"  [{', '.join(marks)}] {a} — {w}")
    print(f"\n## DUPLICATS de títol candidats ({len(dups)}):")
    for a, w1, w2 in dups:
        print(f"  {a}: '{w1}'  <=>  '{w2}'")

    problems = len(garbage) + len(tiny) + len(markup) + len(dups)
    print(f"\nTotal problemes: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
