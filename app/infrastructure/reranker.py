"""CrossEncoderReranker: reordena candidats del retrieval amb un cross-encoder
multilingüe LOCAL (sentence-transformers), sense cap crida a API externa.

Per què: l'embedder actual (bi-encoder, paraphrase-multilingual-MiniLM-L12-v2)
codifica consulta i passatge PER SEPARAT i els compara per cosinus -- ràpid
(permet indexar 400k+ chunks) però perd matisos d'interacció consulta-passatge.
Un cross-encoder llegeix consulta+passatge JUNTS i puntua la rellevància
directament: molt més precís, però massa lent per escanejar tot el corpus.
Per això només s'aplica a un pool petit de candidats (p. ex. 40) que l'embedder
ja ha pre-seleccionat, no a la cerca sencera -- el millor dels dos mons.
"""
from __future__ import annotations
import logging

from app.domain.models import RetrievedChunk

_log = logging.getLogger("sigphi")


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return candidates
        pairs = [(query, rc.chunk.text) for rc in candidates]
        try:
            scores = self._model.predict(pairs)
        except Exception:
            # Degradació amb gràcia: mai trencar el retrieval per un fallo del
            # reranker; es manté l'ordre de l'embedder (ja és un resultat vàlid).
            _log.warning("Reranker ha fallat; es manté l'ordre de l'embedder", exc_info=True)
            return candidates[:top_k]
        order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
        return [candidates[i] for i in order[:top_k]]
