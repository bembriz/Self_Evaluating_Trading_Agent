"""Tests de inserción de reflexiones en memoria (Fase 11, PRD §34-35)."""

from collections.abc import Sequence

import pytest

from application.ports.memory_repository import ScoredMemory
from application.services.memory_writer import MemoryWriter
from domain.evaluation.outcome import TradeOutcome, TradeResult
from domain.memory.guards import MemoryLeakageError
from domain.memory.memory import TradingMemory
from domain.memory.reflection import Reflection, ReflectionResult
from domain.portfolio.portfolio import Trade


class FakeEmbeddings:
    @property
    def model_name(self) -> str:
        return "fake-e5"

    @property
    def dimension(self) -> int:
        return 4

    def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeRepo:
    def __init__(self) -> None:
        self.saved: list[TradingMemory] = []
        self.reflections: list[Reflection] = []

    async def save_memory(self, item: TradingMemory) -> None:
        self.saved.append(item)

    async def save_reflection(self, reflection: Reflection) -> None:
        self.reflections.append(reflection)

    async def search_similar(
        self,
        q: Sequence[float],
        *,
        k: int,
        decision_timestamp_ms: int,
        embedding_space: str,
    ) -> list[ScoredMemory]:
        return []

    async def count_memories(self) -> int:
        return len(self.saved)


def _outcome(closed_at_ms: int = 2000) -> TradeOutcome:
    trade = Trade(
        entry_ts=1000,
        exit_ts=2000,
        entry_price=2000.0,
        exit_price=2020.0,
        quantity=0.5,
        gross_pnl=10.0,
        fees=1.0,
        slippage=1.0,
        net_pnl=8.0,
    )
    return TradeOutcome(trade=trade, result=TradeResult.WIN, mfe=20.0, mae=2.0, r_multiple=None)


def _reflection(closed_at_ms: int = 2000) -> Reflection:
    return Reflection(
        id="r1", outcome_closed_at_ms=closed_at_ms, result=ReflectionResult.WIN, lesson="ok"
    )


async def test_inserts_memory_with_embedding_and_metadata() -> None:
    repo = FakeRepo()
    writer = MemoryWriter(
        embeddings=FakeEmbeddings(),
        repository=repo,
        embedding_space="fastembed|fake-e5|4",
        strategy_version="baseline-v1",
        prompt_version="v001",
        llm_model="deepseek-v4-flash",
        experiment_id="exp123",
    )
    mem = await writer.persist(reflection=_reflection(), outcome=_outcome())
    assert len(repo.saved) == 1 and len(repo.reflections) == 1
    assert mem.embedding == (0.1, 0.2, 0.3, 0.4)
    assert mem.strategy_version == "baseline-v1"
    assert mem.experiment_id == "exp123"
    assert "WIN" in mem.text or "win" in mem.text.lower()


async def test_rejects_unclosed_outcome() -> None:
    writer = MemoryWriter(
        embeddings=FakeEmbeddings(),
        repository=FakeRepo(),
        embedding_space="s",
        strategy_version="v",
        prompt_version="v1",
        llm_model="m",
        experiment_id="e",
    )
    with pytest.raises(ValueError, match="cerrado"):
        await writer.persist(reflection=_reflection(closed_at_ms=500), outcome=_outcome())


async def test_leakage_guard_blocks_future_memory() -> None:
    writer = MemoryWriter(
        embeddings=FakeEmbeddings(),
        repository=FakeRepo(),
        embedding_space="s",
        strategy_version="v",
        prompt_version="v1",
        llm_model="m",
        experiment_id="e",
    )
    with pytest.raises(MemoryLeakageError):
        await writer.persist(
            reflection=_reflection(), outcome=_outcome(), decision_timestamp_ms=1000
        )  # outcome 2000 >= decisión 1000
