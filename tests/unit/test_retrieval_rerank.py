"""Tests del cablejat del reranker a RetrievalService (app/services/retrieval.py)
i de la degradació amb gràcia de CrossEncoderReranker (app/infrastructure/reranker.py).

NO testegen la detecció d'autors/tradicions (ja complexa i separada); NOMÉS que:
  - sense reranker, el comportament és el mateix d'abans (pool = top_k).
  - amb reranker, es demana un pool més gran i es respecta EL SEU ordre.
  - el camí de "tradició nucli" (garantia de representació) NO es reordena.
  - un reranker que peta degrada amb gràcia (no trenca el retrieval).
"""
from __future__ import annotations
from pathlib import Path

from app.domain.models import Chunk, RetrievedChunk
from app.infrastructure.reranker import CrossEncoderReranker
from app.services.retrieval import RetrievalService

_ALIASES_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "authors_aliases.json"


def _rc(i: int, author="Seneca", work="Letters") -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=f"c{i}#0", text=f"passatge {i}", author=author, work=work,
            language="English", completeness="Complete work",
            authorship="Written by the author", note="—",
        ),
        score=1.0 - i * 0.01,  # ordre de l'embedder: 0 és el millor
    )


class _FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    @property
    def dimension(self) -> int:
        return 1


class _FakeVectorDB:
    """Simula un índex on l'ordre de `chunks` JA és l'ordre per similitud."""

    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks
        self.last_top_k: int | None = None  # per inspeccionar quin pool s'ha demanat

    def initialize_index(self, dim: int) -> None:
        pass

    def upsert_batches(self, chunks, vectors, batch_size=100) -> int:
        return 0

    def query_similarity(self, vector, top_k, author_filter=None):
        self.last_top_k = top_k
        pool = self._chunks
        if author_filter:
            pool = [rc for rc in pool if rc.chunk.author in author_filter]
        return pool[:top_k]


class _ReverseReranker:
    """Reranker fals: inverteix l'ordre rebut. Si el resultat surt invertit,
    demostra que REALMENT s'ha cridat (i amb quins candidats)."""

    def rerank(self, query, candidates, top_k):
        return list(reversed(candidates))[:top_k]


class _BrokenReranker:
    def rerank(self, query, candidates, top_k):
        raise RuntimeError("model petat")


def test_without_reranker_pool_is_top_k():
    chunks = [_rc(i) for i in range(10)]
    vdb = _FakeVectorDB(chunks)
    svc = RetrievalService(_FakeEmbedder(), vdb, _ALIASES_PATH, top_k=3)
    result = svc.retrieve("una pregunta qualsevol sense autor")
    assert vdb.last_top_k == 3  # sense reranker, no cal pool extra
    assert [rc.chunk.chunk_id for rc in result] == ["c0#0", "c1#0", "c2#0"]


def test_with_reranker_pool_is_rerank_pool_and_order_is_respected():
    chunks = [_rc(i) for i in range(10)]
    vdb = _FakeVectorDB(chunks)
    svc = RetrievalService(
        _FakeEmbedder(), vdb, _ALIASES_PATH,
        top_k=3, reranker=_ReverseReranker(), rerank_pool=6,
    )
    result = svc.retrieve("una pregunta qualsevol sense autor")
    assert vdb.last_top_k == 6  # ha demanat el pool ampliat, no només top_k
    # el reranker fals inverteix candidates[0:6] -> c5,c4,c3,c2,c1,c0 -> top_k=3
    assert [rc.chunk.chunk_id for rc in result] == ["c5#0", "c4#0", "c3#0"]


def test_reranker_skipped_when_pool_not_larger_than_top_k():
    chunks = [_rc(i) for i in range(2)]  # menys candidats que top_k
    vdb = _FakeVectorDB(chunks)
    svc = RetrievalService(
        _FakeEmbedder(), vdb, _ALIASES_PATH,
        top_k=5, reranker=_ReverseReranker(), rerank_pool=40,
    )
    result = svc.retrieve("pregunta")
    # només 2 candidats per 5 demanats -> no té sentit reordenar, ordre intacte
    assert [rc.chunk.chunk_id for rc in result] == ["c0#0", "c1#0"]


def test_broken_reranker_degrades_gracefully_via_cross_encoder_reranker():
    reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)  # sense carregar el model real

    class _Boom:
        def predict(self, pairs):
            raise RuntimeError("no s'ha pogut carregar el model")

    reranker._model = _Boom()
    candidates = [_rc(i) for i in range(5)]
    result = reranker.rerank("q", candidates, top_k=3)
    # degradació: manté l'ordre original, mai peta
    assert [rc.chunk.chunk_id for rc in result] == ["c0#0", "c1#0", "c2#0"]


def test_cross_encoder_reranker_reorders_by_predicted_score():
    reranker = CrossEncoderReranker.__new__(CrossEncoderReranker)

    class _FakeModel:
        def predict(self, pairs):
            # puntua més alt els passatges amb número més alt (invers a l'ordre d'entrada)
            return [float(i) for i in range(len(pairs))]

    reranker._model = _FakeModel()
    candidates = [_rc(i) for i in range(4)]  # c0..c3, scores 0..3 -> millor és c3
    result = reranker.rerank("q", candidates, top_k=2)
    assert [rc.chunk.chunk_id for rc in result] == ["c3#0", "c2#0"]
