from typing import Any

from application.ports.paper_trading import PaperTradeEvent
from application.services.decision_context import DecisionContext, recompute_decision_contexts
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from domain.market.candle import Candle

TF_MS = 15 * 60_000


def _candle(ts: int, close: float) -> Candle:
    return Candle(ts, close - 1.0, close + 1.0, close - 2.0, close, 10.0, 1000.0)


def _uptrend(n: int, start: float = 100.0, step: float = 0.5) -> list[Candle]:
    return [_candle(i * TF_MS, start + i * step) for i in range(n)]


class FakeRepo:
    async def add(self, event: PaperTradeEvent) -> None:
        pass

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return []


def _config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="s",
    )


def _persisted_contexts(candles: list[Candle]) -> list[dict[str, Any]]:
    runner = PaperRunner(config=_config(), event_repo=FakeRepo())
    contexts: list[dict[str, Any]] = []
    for c in candles:
        event = runner._process("ETHUSDT", "15m", c)
        assert event.decision_context is not None
        contexts.append(event.decision_context)
    return contexts


def test_recompute_equals_persisted_snapshot() -> None:
    candles = _uptrend(80)
    persisted = _persisted_contexts(candles)
    recomputed = recompute_decision_contexts(candles)
    for p, r in zip(persisted, recomputed, strict=True):
        assert DecisionContext.from_dict(p) == r


def test_truncated_dataset_equals_full_dataset_at_T() -> None:
    candles = _uptrend(90)
    full = recompute_decision_contexts(candles)
    for t in range(0, 90, 13):
        truncated = recompute_decision_contexts(candles[: t + 1])
        assert truncated[t] == full[t]


def test_mutating_future_candles_does_not_change_decision_at_T() -> None:
    candles = _uptrend(90)
    t = 40
    before = recompute_decision_contexts(candles)[t]
    mutated = list(candles)
    for i in range(t + 1, len(mutated)):
        mutated[i] = _candle(mutated[i].timestamp_ms, 500.0 + i)
    after = recompute_decision_contexts(mutated)[t]
    assert before == after


def test_recompute_decision_at_T_uses_only_past_candles() -> None:
    # El contexto en T es idéntico se compute sobre el dataset completo o truncado en T.
    candles = _uptrend(60)
    t = 30
    full = recompute_decision_contexts(candles)[t]
    truncated = recompute_decision_contexts(candles[: t + 1])[t]
    assert full == truncated
