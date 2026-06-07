"""RetrievalService: detecció d'autors (12 idiomes) + cerca semàntica amb filtre.

Per què la detecció d'autors:
    Sense filtre, una pregunta sobre "Epictet" podia recuperar fragments de
    Nietzsche per proximitat semàntica. Detectant l'autor anomenat a la consulta
    (en qualsevol dels 12 idiomes dels àlies) i passant-lo com author_filter,
    la cerca queda restringida a aquell autor. Si el filtre no retorna res,
    es fa una segona cerca sense filtre (fallback) per no deixar l'usuari sense
    resposta.
"""
from __future__ import annotations
import json
from pathlib import Path

from app.domain.interfaces import EmbedderInterface, VectorDBInterface
from app.domain.models import RetrievedChunk


class RetrievalService:
    def __init__(
        self,
        embedder: EmbedderInterface,
        vector_db: VectorDBInterface,
        aliases_path: Path,
        top_k: int = 15,
    ) -> None:
        self._embedder = embedder
        self._vector_db = vector_db
        self._top_k = top_k
        self._alias2author = self._load_aliases(Path(aliases_path))

    @staticmethod
    def _load_aliases(path: Path) -> dict[str, str]:
        """Construeix el mapa àlies(qualsevol idioma) -> autor canònic.

        Només indexa àlies distintius: ASCII de >=5 caràcters o qualsevol cadena
        amb caràcters no-ASCII (xinès, àrab, etc.), per evitar falsos positius
        amb paraules curtes comunes.
        """
        alias2author: dict[str, str] = {}
        if not path.exists():
            return alias2author
        data = json.loads(path.read_text(encoding="utf-8"))
        for canon, names in data.items():
            values = list(names.values()) if isinstance(names, dict) else list(names)
            for v in values + [canon]:
                v = (v or "").strip().lower()
                if v and (len(v) >= 5 or any(ord(c) > 127 for c in v)):
                    alias2author.setdefault(v, canon)
        return alias2author

    def detect_authors(self, query: str) -> list[str]:
        """Retorna els autors canònics anomenats a la consulta (qualsevol idioma)."""
        ql = query.lower()
        found: list[str] = []
        for alias, canon in self._alias2author.items():
            if alias in ql and canon not in found:
                found.append(canon)
        return found

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        """Vectoritza la consulta i recupera top_k; filtra per autor si n'hi ha."""
        qv = self._embedder.embed_query(query)
        authors = self.detect_authors(query)
        if authors:
            res = self._vector_db.query_similarity(
                qv, self._top_k, author_filter=authors
            )
            if res:
                return res
        return self._vector_db.query_similarity(qv, self._top_k)
