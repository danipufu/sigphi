"""Models del domini. Sense dependències externes."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """Unitat indexable: un fragment de text amb metadades de citació i avís."""
    chunk_id: str
    text: str
    author: str
    work: str
    language: str
    completeness: str   # "Complete work" | "Fragments only" | "Selection / partial"
    authorship: str     # "Written by the author" | "Recorded/compiled by others" | "Attributed (...)" | "Anonymous / composite"
    note: str           # avís a mostrar a l'usuari, o "—" si no aplica


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Resultat d'una cerca semàntica: un Chunk + score de similitud [0..1]."""
    chunk: Chunk
    score: float


@dataclass(frozen=True, slots=True)
class Citation:
    """Cita verificable que SigPhi adjunta a la resposta."""
    author: str
    work: str
    section: str | None = None
    note: str = ""
