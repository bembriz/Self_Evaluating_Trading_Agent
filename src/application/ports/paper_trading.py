from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PaperTradeEvent:
    session_id: str
    strategy_version: str
    strategy_hash: str
    decision_source: str
    symbol: str
    timeframe: str
    timestamp_ms: int
    action: str
    filled: bool
    risk_reason: str
    exit_reason: str
    exec_price: float | None
    quantity: float | None
    fee: float
    slippage_cost: float
    equity: float
    kill_switch_active: bool
    decision_context: dict[str, Any] | None = None


class PaperTradeEventRepository(Protocol):
    def add(self, event: PaperTradeEvent) -> Awaitable[None]: ...

    def list_session(self, session_id: str) -> Awaitable[list[PaperTradeEvent]]: ...
