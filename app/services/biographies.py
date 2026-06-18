"""Biografies/notes d'origen per autor, com a CONTEXT EDITORIAL del RAG.

A diferència de les fonts primàries (textos PD citables), aquestes bios són un
rerefons factual (dates, escola, rol, obres) que s'injecta al context de l'LLM
perquè contextualitzi l'autor amb precisió. NO són citables ni es mostren com a
font: el principi de SigPhi (cada afirmació verificable contra una font primària)
es manté intacte. Per als textos anònims/sagrats la "bio" és una nota d'origen.

El fitxer de dades (app/data/biographies.json) es té clau pel nom canònic, igual
que authors_aliases.json i el camp `author:` del header SIGPHI de cada obra.
"""
from __future__ import annotations
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


def _norm(s: str) -> str:
    """Minúscules + sense accents, per a un emparellament robust de noms."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


@lru_cache(maxsize=4)
def load_biographies(path: str | Path) -> dict[str, str]:
    """Carrega biographies.json -> {nom_normalitzat: text}. Cau a {} si no existeix.

    Les claus que comencen per '_' (p. ex. '_comment') s'ignoren. Cachejat per ruta.
    """
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        _norm(k): v.strip()
        for k, v in data.items()
        if not k.startswith("_") and isinstance(v, str) and v.strip()
    }


def background_block(authors: list[str], bios: dict[str, str]) -> str:
    """Bloc de rerefons editorial per als autors donats (ordre d'entrada, sense
    duplicats). Retorna '' si no n'hi ha cap amb bio. El text deixa BEN CLAR que
    NO és una font citable."""
    if not bios:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for a in authors:
        key = _norm(a)
        if key in seen or key not in bios:
            continue
        seen.add(key)
        lines.append(f"- {a}: {bios[key]}")
    if not lines:
        return ""
    return (
        "AUTHOR BACKGROUND (editorial context only — NOT a source; never cite this, "
        "never attribute any claim to it; it serves only to identify the author "
        "accurately. All substantive claims must still come from the primary sources "
        "below):\n" + "\n".join(lines)
    )
