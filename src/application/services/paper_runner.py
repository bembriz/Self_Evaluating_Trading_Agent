from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from application.ports.paper_trading import PaperTradeEvent, PaperTradeEventRepository
from application.services.paper_engine import PaperEngine
from application.services.regime_confirmation import RegimeConfirmationTracker
from domain.market.candle import Candle
from domain.market.regime import RegimeClassifier
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


def write_periodic_report(
    summary: PaperRunSummary,
    report_path: Path,
    *,
    regime_evidence: list[dict[str, object]] | None = None,
    rejected_regime_candidates: int = 0,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    delta_fills = summary.delta_fills if summary.delta_fills is not None else "n/a"
    delta_pnl = (
        f"{summary.delta_pnl_absolute:.8f}" if summary.delta_pnl_absolute is not None else "n/a"
    )
    delta_pnl_pct = f"{summary.delta_pnl_pct:.8f}" if summary.delta_pnl_pct is not None else "n/a"
    evidence = regime_evidence or []
    confirmation_candles = next(
        (
            item["confirmation_candles"]
            for item in evidence
            if isinstance(item.get("confirmation_candles"), int)
        ),
        3,
    )
    classifier_version = next(
        (
            item["classifier_version"]
            for item in evidence
            if isinstance(item.get("classifier_version"), str)
        ),
        RegimeClassifier.version,
    )
    regime_names = ", ".join(name for item in evidence if isinstance(name := item.get("name"), str))
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
                f"regime_confirmation_candles: {confirmation_candles}",
                f"regime_classifier_version: {classifier_version}",
                f"confirmed_market_regimes: {regime_names}",
                f"rejected_regime_candidates: {rejected_regime_candidates}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _merge_regime_evidence(
    previous: object, current: list[dict[str, object]]
) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for item in [*previous, *current] if isinstance(previous, list) else current:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        existing = merged.get(name)
        if existing is None:
            merged[name] = dict(item)
            continue
        combined = {**existing, **item}
        for field in ("first_seen_at_ms", "confirmed_at_ms"):
            values = [value.get(field) for value in (existing, item)]
            ints = [value for value in values if isinstance(value, int)]
            if ints:
                combined[field] = min(ints)
        values = [value.get("last_seen_at_ms") for value in (existing, item)]
        ints = [value for value in values if isinstance(value, int)]
        if ints:
            combined["last_seen_at_ms"] = max(ints)
        merged[name] = combined
    return list(merged.values())


def _existing_report_paths(paths: object) -> list[str]:
    if not isinstance(paths, list):
        return []
    return list(
        dict.fromkeys(path for path in paths if isinstance(path, str) and Path(path).exists())
    )


def load_certification_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("certification state must be a JSON object")
    return data


def write_certification_state(
    summary: PaperRunSummary,
    state_path: Path,
    previous: dict[str, Any] | None = None,
    *,
    regime_evidence: list[dict[str, object]] | None = None,
    report_path: Path | None = None,
) -> None:
    first = summary.first_timestamp_ms
    latest = summary.latest_timestamp_ms
    calendar_days = 0
    if first is not None and latest is not None:
        calendar_days = max(1, ((latest - first) // 86_400_000) + 1)
    data = dict(previous or {})
    reports = data.get("periodic_reports", [])
    if report_path is not None:
        reports = [*reports, str(report_path)] if isinstance(reports, list) else [str(report_path)]
    data.update(
        {
            "strategy_version": summary.strategy_version,
            "strategy_hash": summary.strategy_hash,
            "active_strategy_hash": summary.strategy_hash,
            "calendar_days": calendar_days,
            "trade_count": summary.fills,
            "market_regimes": _merge_regime_evidence(
                data.get("market_regimes", []), regime_evidence or []
            ),
            "periodic_reports": _existing_report_paths(reports),
            "latest_equity": summary.latest_equity,
            "initial_equity": summary.initial_equity,
            "pnl_absolute": summary.pnl_absolute,
            "pnl_pct": summary.pnl_pct,
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
    temporary_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(state_path)


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
        regime_classifier: RegimeClassifier | None = None,
    ) -> None:
        config.validate_safe()
        self._config = config
        self._repo = event_repo
        self._strategy = strategy or EmaRsiBaseline()
        self._engine = paper_engine or PaperEngine(config=RiskConfig())
        self._strategy_hash = strategy_hash(self._strategy.version, config.decision_source)
        self._regime_classifier = regime_classifier or RegimeClassifier()
        self._candles_by_symbol: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=100))
        self._regime_trackers = {
            symbol: RegimeConfirmationTracker(symbol=symbol, timeframe=config.timeframe)
            for symbol in config.symbols
        }

    @property
    def rejected_regime_candidates(self) -> int:
        return sum(tracker.rejected_candidates for tracker in self._regime_trackers.values())

    def regime_evidence(self) -> list[dict[str, object]]:
        return [
            evidence
            for tracker in self._regime_trackers.values()
            for evidence in tracker.evidence()
        ]

    async def handle_kline(self, kline: KlineUpdate) -> PaperTradeEvent | None:
        candle = kline.to_candle()
        if candle is None:
            return None
        candles = self._candles_by_symbol[kline.symbol]
        candles.append(candle)
        self._regime_trackers[kline.symbol].observe(
            self._regime_classifier.classify(candles), candle.timestamp_ms
        )
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
