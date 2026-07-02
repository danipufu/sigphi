"""Tests de la cerca lèxica BM25 (FTS5) de ChunkStore, per a la cerca híbrida."""
from __future__ import annotations

from app.domain.models import Chunk
from app.infrastructure.chunk_store import ChunkStore


def _chunk(cid, text, author="Seneca", work="Letters"):
    return Chunk(
        chunk_id=cid, text=text, author=author, work=work, language="English",
        completeness="Complete work", authorship="Written by the author", note="—",
    )


def test_search_bm25_finds_exact_word_match(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([
        _chunk("a#0", "Epictetus taught that what is in our control matters most."),
        _chunk("b#0", "Marcus Aurelius wrote about the nature of the cosmos."),
    ])
    hits = store.search_bm25("Epictetus control", top_k=5)
    assert len(hits) >= 1
    assert hits[0].chunk.chunk_id == "a#0"
    store.close()


def test_search_bm25_respects_author_filter(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([
        _chunk("a#0", "the concept of virtue in philosophy", author="Aristotle"),
        _chunk("b#0", "the concept of virtue in philosophy", author="Confucius"),
    ])
    hits = store.search_bm25("virtue philosophy", top_k=5, author_filter=["Confucius"])
    assert len(hits) == 1
    assert hits[0].chunk.author == "Confucius"
    store.close()


def test_search_bm25_empty_query_returns_empty(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([_chunk("a#0", "some text")])
    assert store.search_bm25("", top_k=5) == []
    assert store.search_bm25("!!! ??? ...", top_k=5) == []  # sense paraules reals
    store.close()


def test_search_bm25_no_match_returns_empty(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([_chunk("a#0", "philosophy and virtue")])
    assert store.search_bm25("xenomorphic quantum tachyons", top_k=5) == []
    store.close()


def test_fts_index_updated_on_upsert_replace(tmp_path):
    """INSERT OR REPLACE (ingesta resumible) no ha de duplicar ni deixar text
    vell indexat a chunks_fts."""
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([_chunk("a#0", "original wording about ethics")])
    assert len(store.search_bm25("ethics", top_k=5)) == 1
    store.upsert_many([_chunk("a#0", "replaced wording about aesthetics")])
    assert len(store.search_bm25("ethics", top_k=5)) == 0  # text vell fora
    assert len(store.search_bm25("aesthetics", top_k=5)) == 1  # text nou dins
    store.close()


def test_fts_index_updated_on_delete(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([_chunk("a#0", "unique searchable phrase here")])
    assert len(store.search_bm25("searchable phrase", top_k=5)) == 1
    store.delete_ids(["a#0"])
    assert store.search_bm25("searchable phrase", top_k=5) == []
    store.close()


def test_backfill_indexes_preexisting_chunks(tmp_path):
    """Simula una BD d'ABANS que existís chunks_fts: insereix directament a la
    taula base (saltant-se upsert_many) i comprova que el pròxim __init__
    (nova connexió, com passaria en un redeploy) fa el backfill sol."""
    path = tmp_path / "chunks.sqlite"
    store1 = ChunkStore(path)
    store1._conn.execute(
        "INSERT INTO chunks (chunk_id, text, author, work, language,"
        " completeness, authorship, note) VALUES (?,?,?,?,?,?,?,?)",
        ("legacy#0", "a legacy chunk about stoicism", "Seneca", "Letters",
         "English", "Complete work", "Written by the author", "—"),
    )
    store1._conn.commit()
    # confirma que, tal com esperem del setup, chunks_fts encara NO té aquest chunk
    assert store1.search_bm25("stoicism", top_k=5) == []
    store1.close()

    store2 = ChunkStore(path)  # __init__ -> _backfill_fts_if_needed()
    hits = store2.search_bm25("stoicism", top_k=5)
    assert len(hits) == 1 and hits[0].chunk.chunk_id == "legacy#0"
    store2.close()


def test_search_bm25_ordering_prefers_more_term_matches(tmp_path):
    store = ChunkStore(tmp_path / "chunks.sqlite")
    store.upsert_many([
        _chunk("a#0", "stoicism virtue"),           # les dues paraules
        _chunk("b#0", "stoicism and other topics"),  # només una
    ])
    hits = store.search_bm25("stoicism virtue", top_k=5)
    assert hits[0].chunk.chunk_id == "a#0"
    store.close()
