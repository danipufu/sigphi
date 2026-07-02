"""Tests de TelemetryStore (registre de torns + feedback)."""
from __future__ import annotations

import pytest

from app.services.telemetry import TelemetryStore


@pytest.fixture
def store(tmp_path):
    s = TelemetryStore(tmp_path / "telemetry.sqlite")
    yield s
    s.close()


def test_empty_stats(store):
    stats = store.stats()
    assert stats["turns"] == 0
    assert stats["no_sources_rate"] is None
    assert stats["feedback_up"] == 0 and stats["feedback_down"] == 0


def test_record_turn_basic_counts(store):
    store.record_turn("Què deia Epictet?", authors=["Epictetus"], n_retrieved=5,
                       top_score=0.72, sources_count=3, no_sources=False,
                       suggestions_count=3, unverified_count=0, latency_ms=1200)
    stats = store.stats()
    assert stats["turns"] == 1
    assert stats["no_sources_rate"] == 0.0
    assert stats["avg_top_score"] == pytest.approx(0.72)
    assert stats["avg_latency_ms"] == 1200
    assert stats["avg_sources_per_turn"] == pytest.approx(3.0)


def test_no_sources_rate_computed_correctly(store):
    store.record_turn("Bon dia", no_sources=True)
    store.record_turn("Bon dia", no_sources=True)
    store.record_turn("Què deia Sèneca de la mort?", no_sources=False, sources_count=2)
    stats = store.stats()
    assert stats["turns"] == 3
    assert stats["no_sources_rate"] == pytest.approx(2 / 3, rel=1e-3)


def test_unverified_citations_accumulate(store):
    store.record_turn("q1", unverified_count=1)
    store.record_turn("q2", unverified_count=2)
    assert store.stats()["unverified_citations_total"] == 3


def test_feedback_up_and_down(store):
    store.record_feedback("Què deia Plató?", vote=1)
    store.record_feedback("Què deia Plató?", vote=1)
    store.record_feedback("Resposta dolenta", vote=-1)
    stats = store.stats()
    assert stats["feedback_up"] == 2
    assert stats["feedback_down"] == 1


def test_feedback_vote_normalized_to_plus_or_minus_one(store):
    store.record_feedback("q", vote=5)   # qualsevol positiu -> +1
    store.record_feedback("q", vote=-99)  # qualsevol no-positiu -> -1
    store.record_feedback("q", vote=0)    # 0 -> -1 (no és amunt)
    stats = store.stats()
    assert stats["feedback_up"] == 1
    assert stats["feedback_down"] == 2


def test_top_queries_ordered_by_frequency(store):
    for _ in range(3):
        store.record_turn("pregunta popular")
    store.record_turn("pregunta rara")
    top = store.stats()["top_queries"]
    assert top[0] == {"query": "pregunta popular", "count": 3}


def test_query_length_is_capped(store):
    long_q = "x" * 1000
    store.record_turn(long_q)
    top = store.stats()["top_queries"]
    assert len(top[0]["query"]) == 500


def test_stats_respects_days_window(store):
    store.record_turn("q avui")
    stats_0_days = store.stats(days=0)  # finestra buida (cap torn "ts >= ara")
    assert stats_0_days["turns"] == 0
    stats_wide = store.stats(days=30)
    assert stats_wide["turns"] == 1


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "telemetry.sqlite"
    s1 = TelemetryStore(path)
    s1.record_turn("q", sources_count=2)
    s1.record_feedback("q", vote=1)
    s1.close()
    s2 = TelemetryStore(path)
    stats = s2.stats()
    assert stats["turns"] == 1
    assert stats["feedback_up"] == 1
    s2.close()
