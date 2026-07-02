"""Tests de la cerca híbrida (semàntica + BM25 lèxica, fusionades amb RRF) a
RetrievalService. Complementa test_retrieval_rerank.py (reranker) i
test_chunk_store_bm25.py (BM25 en si); aquí NOMÉS el cablejat de la fusió."""
from __future__ import annotations
from pathlib import Path

from app.domain.models import Chunk, RetrievedChunk
from app.services.retrieval import RetrievalService, _rrf_merge

_ALIASES_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "authors_aliases.json"


def _rc(cid: str, score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=cid, text="t", author="Seneca", work="Letters", language="English",
            completeness="Complete work", authorship="Written by the author", note="—",
        ),
        score=score,
    )


# --- _rrf_merge (funció pura) -------------------------------------------------

def test_rrf_merge_single_list_preserves_order():
    lst = [_rc("a"), _rc("b"), _rc("c")]
    assert [rc.chunk.chunk_id for rc in _rrf_merge([lst], top_k=3)] == ["a", "b", "c"]


def test_rrf_merge_boosts_items_ranked_high_in_both_lists():
    # "b" és 2n a la llista 1 però 1r a la llista 2 -> hauria de guanyar a "a"
    # (1r a la llista 1 però absent de la 2).
    list_a = [_rc("a"), _rc("b"), _rc("c")]
    list_b = [_rc("b"), _rc("d"), _rc("e")]
    merged = _rrf_merge([list_a, list_b], top_k=5)
    assert merged[0].chunk.chunk_id == "b"


def test_rrf_merge_dedupes_same_chunk_across_lists():
    list_a = [_rc("a"), _rc("b")]
    list_b = [_rc("a"), _rc("c")]
    merged = _rrf_merge([list_a, list_b], top_k=10)
    ids = [rc.chunk.chunk_id for rc in merged]
    assert ids.count("a") == 1
    assert set(ids) == {"a", "b", "c"}


def test_rrf_merge_respects_top_k():
    lst = [_rc(str(i)) for i in range(10)]
    assert len(_rrf_merge([lst], top_k=3)) == 3


def test_rrf_merge_empty_lists():
    assert _rrf_merge([[], []], top_k=5) == []


# --- Cablejat a RetrievalService ----------------------------------------------

class _FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    @property
    def dimension(self) -> int:
        return 1


class _FakeVectorDB:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    def initialize_index(self, dim: int) -> None:
        pass

    def upsert_batches(self, chunks, vectors, batch_size=100) -> int:
        return 0

    def query_similarity(self, vector, top_k, author_filter=None):
        pool = self._chunks
        if author_filter:
            pool = [rc for rc in pool if rc.chunk.author in author_filter]
        return pool[:top_k]


class _FakeLexical:
    """Retorna una llista FIXA (simula BM25 trobant un chunk per paraula exacta
    que la cerca semàntica no tenia entre els seus millors)."""

    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.called_with: str | None = None

    def search_bm25(self, query, top_k, author_filter=None):
        self.called_with = query
        return self._hits[:top_k]


def test_without_lexical_behaves_like_semantic_only():
    dense = [_rc("d0"), _rc("d1"), _rc("d2")]
    svc = RetrievalService(_FakeEmbedder(), _FakeVectorDB(dense), _ALIASES_PATH, top_k=2)
    result = svc.retrieve("pregunta")
    assert [rc.chunk.chunk_id for rc in result] == ["d0", "d1"]


def test_lexical_hit_absent_from_dense_still_surfaces():
    dense = [_rc("d0"), _rc("d1"), _rc("d2")]
    lexical_only = [_rc("lex_unique")]  # no apareix a `dense`
    lex = _FakeLexical(lexical_only)
    svc = RetrievalService(_FakeEmbedder(), _FakeVectorDB(dense), _ALIASES_PATH, top_k=4, lexical=lex)
    result = svc.retrieve("pregunta amb un nom propi concret")
    ids = [rc.chunk.chunk_id for rc in result]
    assert "lex_unique" in ids
    assert lex.called_with == "pregunta amb un nom propi concret"


def test_lexical_empty_falls_back_to_dense_only():
    dense = [_rc("d0"), _rc("d1")]
    lex = _FakeLexical([])  # BM25 no troba res
    svc = RetrievalService(_FakeEmbedder(), _FakeVectorDB(dense), _ALIASES_PATH, top_k=2, lexical=lex)
    result = svc.retrieve("pregunta")
    assert [rc.chunk.chunk_id for rc in result] == ["d0", "d1"]


def test_item_ranked_high_in_both_dense_and_lexical_comes_first():
    shared = _rc("shared")
    dense = [_rc("d0"), shared, _rc("d1")]
    lex = _FakeLexical([shared, _rc("lex_only")])
    svc = RetrievalService(_FakeEmbedder(), _FakeVectorDB(dense), _ALIASES_PATH, top_k=4, lexical=lex)
    result = svc.retrieve("pregunta")
    assert result[0].chunk.chunk_id == "shared"
