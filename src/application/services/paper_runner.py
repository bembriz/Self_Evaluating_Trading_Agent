from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.ports.paper_trading import PaperTradeEvent, PaperTradeEventRepository
from application.services.paper_engine import PaperEngine
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.signal import Intensity
from domain.trading.strategy import EmaRsiBaseline


class UnsafePaperModeError(RuntimeError):
    pass


def strategy_hash(strategy_version: str, decision_source: str) -> str:
    payload = f"{decision_source}:{strategy_version}".encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperRunSummary:
    session_id: str
    decision_source: str
    strategy_version: str
    strategy_hash: str
    symbol: str
    timeframe: str
    first_timestamp_ms: int | None
    latest_timestamp_ms: int | None
    decisions: dict[str, int]
    fills: int
    fees: float
    slippage: float
    latest_equity: float
    kill_switch_active: bool
    initial_equity: float = 1000.0
    pnl_absolute: float = 0.0
    pnl_pct: float = 0.0
    delta_decisions: dict[str, int] | None = None
    delta_fills: int | None = None
    delta_pnl_absolute: float | None = None
    delta_pnl_pct: float | None = None


def summarize_events(
    events: list[PaperTradeEvent],
    previous: PaperRunSummary | None = None,
    *,
    initial_equity: float = 1000.0,
) -> PaperRunSummary:
    decisions = {"BUY": 0, "SELL": 0, "HOLD": 0}
    ordered = sorted(events, key=lambda event: event.timestamp_ms)
    for event in ordered:
        decisions[event.action] = decisions.get(event.action, 0) + 1
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None
    latest_equity = last.equity if last else initial_equity
    pnl_absolute = latest_equity - initial_equity
    pnl_pct = pnl_absolute / initial_equity if initial_equity else 0.0
    if previous is None:
        delta_decisions: dict[str, int] | None = None
        delta_fills: int | None = None
        delta_pnl_absolute: float | None = None
        delta_pnl_pct: float | None = None
    else:
        delta_decisions = {
            action: decisions.get(action, 0) - previous.decisions.get(action, 0)
            for action in ("BUY", "SELL", "HOLD")
        }
        delta_fills = sum(1 for event in ordered if event.filled) - previous.fills
        delta_pnl_absolute = pnl_absolute - previous.pnl_absolute
        delta_pnl_pct = pnl_pct - previous.pnl_pct
    return PaperRunSummary(
        session_id=first.session_id if first else "",
        decision_source=first.decision_source if first else "baseline",
        strategy_version=first.strategy_version if first else "",
        strategy_hash=first.strategy_hash if first else "",
        symbol=first.symbol if first else "",
        timeframe=first.timeframe if first else "",
        first_timestamp_ms=first.timestamp_ms if first else None,
        latest_timestamp_ms=last.timestamp_ms if last else None,
        decisions=decisions,
        fills=sum(1 for event in ordered if event.filled),
        fees=sum(event.fee for event in ordered),
        slippage=sum(event.slippage_cost for event in ordered),
        latest_equity=latest_equity,
        kill_switch_active=last.kill_switch_active if last else False,
        initial_equity=initial_equity,
        pnl_absolute=pnl_absolute,
        pnl_pct=pnl_pct,
        delta_decisions=delta_decisions,
        delta_fills=delta_fills,
        delta_pnl_absolute=delta_pnl_absolute,
        delta_pnl_pct=delta_pnl_pct,
    )


def write_periodic_report(summary: PaperRunSummary, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    delta_fills = summary.delta_fills if summary.delta_fills is not None else "n/a"
    delta_pnl = (
        f"{summary.delta_pnl_absolute:.8f}" if summary.delta_pnl_absolute is not None else "n/a"
    )
    delta_pnl_pct = f"{summary.delta_pnl_pct:.8f}" if summary.delta_pnl_pct is not None else "n/a"
    report_path.write_text(
        "\n".join(
            [
                "# Paper Trading Periodic Report",
                "",
                f"session_id: {summary.session_id}",
                f"decision_source: {summary.decision_source}",
                f"strategy_version: {summary.strategy_version}",
                f"strategy_hash: {summary.strategy_hash}",
                f"symbol: {summary.symbol}",
                f"timeframe: {summary.timeframe}",
                f"first_timestamp_ms: {summary.first_timestamp_ms}",
                f"latest_timestamp_ms: {summary.latest_timestamp_ms}",
                f"buy_decisions: {summary.decisions.get('BUY', 0)}",
                f"sell_decisions: {summary.decisions.get('SELL', 0)}",
                f"hold_decisions: {summary.decisions.get('HOLD', 0)}",
                f"fills: {summary.fills}",
                f"fees: {summary.fees:.8f}",
                f"slippage: {summary.slippage:.8f}",
                f"initial_equity: {summary.initial_equity:.8f}",
                f"latest_equity: {summary.latest_equity:.8f}",
                f"pnl_absolute: {summary.pnl_absolute:.8f}",
                f"pnl_pct: {summary.pnl_pct:.8f}",
                f"delta_fills: {delta_fills}",
                f"delta_pnl_absolute: {delta_pnl}",
                f"delta_pnl_pct: {delta_pnl_pct}",
                f"kill_switch_active: {summary.kill_switch_active}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_certification_state(
    summary: PaperRunSummary,
    state_path: Path,
    previous: dict[str, Any] | None = None,
) -> None:
    first = summary.first_timestamp_ms
    latest = summary.latest_timestamp_ms
    calendar_days = 0
    if first is not None and latest is not None:
        calendar_days = max(1, ((latest - first) // 86_400_000) + 1)
    data = dict(previous or {})
    data.update(
        {
            "strategy_version": summary.strategy_version,
            "strategy_hash": summary.strategy_hash,
            "active_strategy_hash": summary.strategy_hash,
            "calendar_days": calendar_days,
            "trade_count": summary.fills,
            "market_regimes": data.get("market_regimes", []),
            "periodic_reports": [
                report
                for report in data.get("periodic_reports", [])
                if isinstance(report, str) and Path(report).exists()
            ],
            "latest_equity": summary.latest_equity,
            "initial_equity": summary.initial_equity,
            "pnl_absolute": summary.pnl_absolute,
            "pnl_pct": summary.pnl_pct,
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True, slots=True)
class PaperRunnerConfig:
    trading_mode: str
    live_trading_enabled: bool
    symbols: tuple[str, ...]
    timeframe: str
    session_id: str
    decision_source: str = "baseline"
    report_interval_seconds: int = 24 * 60 * 60
    max_runtime_seconds: int | None = None

    def validate_safe(self) -> None:
        if self.trading_mode != "paper":
            raise UnsafePaperModeError("TRADING_MODE must be paper for paper-runner")
        if self.live_trading_enabled:
            raise UnsafePaperModeError("LIVE_TRADING_ENABLED must be false for paper-runner")
        if self.decision_source != "baseline":
            raise UnsafePaperModeError(
                "baseline paper-runner only supports decision_source=baseline"
            )
        if not self.symbols:
            raise UnsafePaperModeError("at least one symbol is required")


class PaperRunner:
    def __init__(
        self,
        *,
        config: PaperRunnerConfig,
        event_repo: PaperTradeEventRepository,
        paper_engine: PaperEngine | None = None,
        strategy: EmaRsiBaseline | None = None,
    ) -> None:
        config.validate_safe()
        self._config = config
        self._repo = event_repo
        self._strategy = strategy or EmaRsiBaseline()
        self._engine = paper_engine or PaperEngine(config=RiskConfig())
        self._strategy_hash = strategy_hash(self._strategy.version, config.decision_source)

    async def handle_kline(self, kline: KlineUpdate) -> PaperTradeEvent | None:
        candle = kline.to_candle()
        if candle is None:
            return None
        signal = self._strategy.on_candle(candle)
        decision = TradingDecision(
            timestamp_ms=candle.timestamp_ms,
            action=signal.action,
            confidence=1.0,
            intensity=Intensity.MEDIUM,
            rationale_summary=signal.reason,
        )
        paper_event = self._engine.on_price(
            decision=decision,
            price=candle.close,
            atr=None,
            timestamp_ms=candle.timestamp_ms,
        )
        fill = paper_event.fill
        event = PaperTradeEvent(
            session_id=self._config.session_id,
            strategy_version=self._strategy.version,
            strategy_hash=self._strategy_hash,
            decision_source=self._config.decision_source,
            symbol=kline.symbol,
            timeframe=kline.interval.label,
            timestamp_ms=candle.timestamp_ms,
            action=paper_event.action.name,
            filled=paper_event.filled,
            risk_reason=paper_event.risk_reason,
            exit_reason=paper_event.exit_reason,
            exec_price=fill.exec_price if fill is not None else None,
            quantity=fill.quantity if fill is not None else None,
            fee=fill.fee if fill is not None else 0.0,
            slippage_cost=fill.slippage_cost if fill is not None else 0.0,
            equity=self._engine.mark_to_market(price=candle.close),
            kill_switch_active=self._engine.kill_switch_state.active,
        )
        await self._repo.add(event)
        return event

    async def run_once(self) -> None:
        return None
