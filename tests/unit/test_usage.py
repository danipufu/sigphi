"""Tests del UsageMeter (comptador d'ús + tope de despesa)."""
from __future__ import annotations

import pytest

from app.services.usage import UsageMeter


@pytest.fixture
def meter(tmp_path):
    # preus: 1.0 EUR/1M input, 2.0 EUR/1M output (rodons, per facilitar els càlculs)
    m = UsageMeter(tmp_path / "usage.sqlite", 1.0, 2.0)
    yield m
    m.close()


def test_empty_meter_zero_cost(meter):
    assert meter.month_cost_eur("2026-06") == 0.0


def test_record_computes_cost(meter):
    meter.record(1_000_000, 0, month="2026-06")  # 1M input -> 1.0 EUR
    assert meter.month_cost_eur("2026-06") == pytest.approx(1.0)
    meter.record(0, 1_000_000, month="2026-06")  # +1M output -> +2.0 EUR
    assert meter.month_cost_eur("2026-06") == pytest.approx(3.0)


def test_record_accumulates_calls(meter):
    meter.record(100, 50, month="2026-06")
    meter.record(100, 50, month="2026-06")
    snap = meter.snapshot(month="2026-06")
    assert snap["calls"] == 2
    assert snap["input_tokens"] == 200
    assert snap["output_tokens"] == 100


def test_months_are_isolated(meter):
    meter.record(1_000_000, 0, month="2026-06")
    assert meter.month_cost_eur("2026-07") == 0.0  # mes nou -> reset implícit
    assert meter.month_cost_eur("2026-06") == pytest.approx(1.0)


def test_snapshot_budget_fields(meter):
    meter.record(1_000_000, 0, month="2026-06")  # 1.0 EUR
    snap = meter.snapshot(budget_eur=10.0, month="2026-06")
    assert snap["budget_eur"] == 10.0
    assert snap["remaining_eur"] == pytest.approx(9.0)
    assert snap["over_budget"] is False


def test_snapshot_over_budget(meter):
    meter.record(0, 10_000_000, month="2026-06")  # 20.0 EUR > 10
    snap = meter.snapshot(budget_eur=10.0, month="2026-06")
    assert snap["over_budget"] is True
    assert snap["remaining_eur"] == 0.0


def test_negative_tokens_clamped(meter):
    meter.record(-5, -5, month="2026-06")
    assert meter.month_cost_eur("2026-06") == 0.0


def test_persists_across_reopen(tmp_path):
    path = tmp_path / "usage.sqlite"
    m1 = UsageMeter(path, 1.0, 2.0)
    m1.record(1_000_000, 0, month="2026-06")
    m1.close()
    m2 = UsageMeter(path, 1.0, 2.0)
    assert m2.month_cost_eur("2026-06") == pytest.approx(1.0)
    m2.close()
