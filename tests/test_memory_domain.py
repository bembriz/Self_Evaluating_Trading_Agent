"""Tests del dominio de memoria (PRD §32-34): items, reflexiones y anti-leakage."""

import pytest

from domain.memory.guards import MemoryLeakageError, assert_no_leakage, filter_leakage
from domain.memory.memory import TradingMemory
from domain.memory.reflection import Reflection, ReflectionResult
from domain.memory.space import build_embedding_space


def _mem(id_: str, outcome_ts: int) -> TradingMemory:
    return TradingMemory(id=id_, text=f"memoria {id_}", outcome_timestamp_ms=outcome_ts)


def test_trading_memory_defaults_backward_compatible() -> None:
    m = _mem("m1", 100)
    assert m.symbol == ""
    assert m.pnl == 0.0
    assert m.embedding == ()
    assert m.strategy_version == ""


def test_reflection_requires_closed_outcome_fields() -> None:
    r = Reflection(
        id="r1",
        outcome_closed_at_ms=500,
        result=ReflectionResult.LOSS,
        primary_error="COUNTER_TREND_ENTRY",
        lesson="señal prematura",
        future_condition="reducir confianza",
    )
    assert r.result is ReflectionResult.LOSS
    assert r.outcome_closed_at_ms == 500


def test_filter_leakage_keeps_only_past_outcomes() -> None:
    items = [_mem("pasada", 900), _mem("futura", 1100)]
    out = filter_leakage(items, decision_timestamp_ms=1000)
    assert [m.id for m in out] == ["pasada"]


def test_filter_leakage_excludes_equal_timestamp_strict() -> None:
    items = [_mem("igual", 1000)]
    assert filter_leakage(items, decision_timestamp_ms=1000) == ()


def test_assert_no_leakage_passes_and_raises() -> None:
    assert_no_leakage([_mem("ok", 999)], decision_timestamp_ms=1000)
    with pytest.raises(MemoryLeakageError):
        assert_no_leakage([_mem("mala", 1001)], decision_timestamp_ms=1000)


def test_embedding_space_is_versioned_tuple() -> None:
    space = build_embedding_space("fastembed", "intfloat/multilingual-e5-small", 384)
    assert space == "fastembed|intfloat/multilingual-e5-small|384"
    other = build_embedding_space("openai", "text-embedding-3-small", 1536)
    assert other != space
