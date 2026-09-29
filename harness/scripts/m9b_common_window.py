#!/usr/bin/env python3
"""M9-B2B — Runner de ventana común OLD (close-only) vs NEW (trade-sequence).

Orquesta la comparación de 647 días sobre el **mismo** Gold Medallion: OLD y NEW
consumen exactamente la misma secuencia de velas 15m y las mismas estrategias;
el runner no define reglas de trading (estrategia, RiskEngine, fills, fees,
slippage y portfolio accounting provienen del runtime existente).

- OLD = `old_close_only`: PaperEngine real con semántica close-only (precio =
  candle.close, ATR = ATR de la vela confirmada) + RiskEngine dinámico.
- NEW = `trade_sequence`: Trade-Level Replay M7 (TRADE_SEQUENCE_TAKER_PROXY),
  fills sobre los trades históricos de Silver.

M9-B2B añade:

- **Streaming obligatorio**: NEW recibe un `Iterable[ReplayTrade]` y lo pasa
  directo al motor (sin `list()`); no se materializan todos los trades Silver.
- **Artefactos deterministas por corrida** (`--output-dir`):
  `<strategy>-<model>-summary.json` + `<strategy>-<model>-trades.jsonl`,
  escritos `.part → verify → rename`; mismo contenido ⇒ SKIP; contenido
  distinto ⇒ FAIL CLOSED.
- **Ledger económico** por trade cerrado (entry/exit ref+exec, fees, slippage,
  net, holding; NEW preserva trigger tss, MFE/MAE, stop/target, versiones).
- **Summary comparable OLD/NEW** con la MISMA definición; max drawdown sobre la
  curva de equity REALIZADA ordenada por cierre de trade
  (`MAX_DRAWDOWN_BASIS=REALIZED_CLOSED_TRADES`).

Paridad de señales obligatoria antes de cualquier lectura económica: ambos
modelos deben reproducir la misma secuencia BUY/SELL/HOLD de 62112 velas.

Uso:
  python3 harness/scripts/m9b_common_window.py \\
      --dataset-dir <Gold replay dataset> --trades-dir <Silver trades> \\
      --candles-dir <Silver candles> --strategy baseline \\
      --model old_close_only [--start 2023-09-09] [--end-exclusive 2025-06-17] \\
      [--output-dir <dir>] [--expect-common-window] \\
      [--require-marker /srv/data/.lenovosrv-data-volume]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:  # harness/scripts → repo/src
    sys.path.insert(0, str(_SRC))

from application.services.paper_engine import PaperEngine  # noqa: E402
from domain.market.candle import Candle  # noqa: E402
from domain.market.indicators import atr as atr_series  # noqa: E402
from domain.risk.config import RiskConfig  # noqa: E402
from domain.trading.decision import TradingDecision  # noqa: E402
from domain.trading.fees import FeeModel  # noqa: E402
from domain.trading.fill import Fill  # noqa: E402
from domain.trading.signal import Action, Intensity  # noqa: E402
from domain.trading.slippage import SlippageModel  # noqa: E402
from domain.trading.strategy import Strategy  # noqa: E402
from infrastructure.medallion import replay_cli  # noqa: E402
from infrastructure.medallion.bronze import ensure_marker  # noqa: E402
from infrastructure.medallion.replay import (  # noqa: E402
    CandleRow,
    ReplayResult,
    ReplayScenario,
    ReplayTrade,
    load_candles,
    replay_engine,
    validate_dataset,
)
from infrastructure.medallion.strategy_provider import (  # noqa: E402
    StrategyDecisionProvider,
    rows_to_domain_candles,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

DAY_MS = 86_400_000
CANDLES_PER_DAY = 96
COMMON_WINDOW_START = date(2023, 9, 9)
COMMON_WINDOW_END_EXCLUSIVE = date(2025, 6, 17)
COMMON_WINDOW_DAYS = 647
EXPECTED_15M_CANDLES = 62112

STRATEGIES = ("baseline", "donchian", "bollinger")
MODELS = ("old_close_only", "trade_sequence")
# Nombre de construcción en `replay_cli._build_strategy` (la baseline del Lab es
# `EmaRsiBaseline`); el runner expone el alias corto `baseline`.
_STRATEGY_BUILD_NAME = {"baseline": "ema-rsi", "donchian": "donchian", "bollinger": "bollinger"}
assert set(_STRATEGY_BUILD_NAME) == set(STRATEGIES)

# Presentación únicamente: PaperEngine legacy emite `llm_sell`; se mapea a
# `strategy_exit` para el reporte conservando el valor raw original.
EXIT_REASON_PRESENTATION = {"llm_sell": "strategy_exit"}

PARITY_SCENARIO_ID = "m9b-common-window-v1"
RISK_VERSION = "risk-v2-atr-exit"
FEE_TAKER_BPS = 10.0
SLIPPAGE_BPS = 2.0
ATR_PERIOD = 14
INTENSITY = "medium"

OLD_EXECUTION_MODEL = "PAPER_ENGINE_CLOSE_ONLY"
NEW_EXECUTION_MODEL = "TRADE_SEQUENCE_TAKER_PROXY"
DEFAULT_CODE_GIT_SHA = "unknown"

MAX_DRAWDOWN_BASIS = "REALIZED_CLOSED_TRADES"
PROFIT_FACTOR_BASIS = "NET_REALIZED"
SUMMARY_SCHEMA_VERSION = "m9b2b-summary-v1"
TRADE_LEDGER_SCHEMA_VERSION = "m9b2b-trade-ledger-v1"

# Campos mínimos del ledger económico: OBLIGATORIOS en ambos modelos.
LEDGER_REQUIRED_FIELDS = (
    "entry_timestamp",
    "exit_timestamp",
    "entry_reference_price",
    "entry_execution_price",
    "exit_reference_price",
    "exit_execution_price",
    "quantity",
    "exit_reason",
    "exit_reason_presentation",
    "gross_reference_pnl",
    "gross_execution_pnl",
    "fees",
    "slippage",
    "net_pnl",
    "holding_ms",
)

# Campos adicionales que NEW debe preservar (cronología de ejecución completa).
LEDGER_EXTENDED_FIELDS = (
    "entry_trigger_timestamp",
    "exit_trigger_timestamp",
    "mfe",
    "mae",
    "stop",
    "target",
    "strategy_version",
    "risk_version",
    "execution_model",
    "execution_model_version",
)

# Identidades que el summary debe exponer (además de model/strategy/metrics).
SUMMARY_IDENTITY_FIELDS = (
    "code_git_sha",
    "dataset_id",
    "dataset_sha",
    "common_window_start",
    "common_window_end_exclusive",
    "candle_hash",
    "signal_hash",
    "strategy_version",
    "risk_version",
    "execution_model",
    "fee_bps",
    "slippage_bps",
    "stop_atr",
    "target_r",
    "trailing_atr",
)


# --------------------------------------------------------------- errores


class ArtifactConflictError(Exception):
    """Artefacto existente con contenido distinto (FAIL CLOSED)."""


# --------------------------------------------------------------- ventana


def day_start_ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) * 1000


def common_window_bounds() -> tuple[int, int]:
    """(START inclusive, END_EXCLUSIVE) de la ventana común en ms UTC."""
    return day_start_ms(COMMON_WINDOW_START), day_start_ms(COMMON_WINDOW_END_EXCLUSIVE)


def window_days(start_ms: int, end_ms: int) -> int:
    if end_ms <= start_ms:
        raise ValueError("ventana inválida: end <= start (FAIL CLOSED)")
    if (end_ms - start_ms) % DAY_MS != 0:
        raise ValueError("ventana no alineada a días UTC (FAIL CLOSED)")
    return (end_ms - start_ms) // DAY_MS


def expected_15m_candles(start_ms: int, end_ms: int) -> int:
    return window_days(start_ms, end_ms) * CANDLES_PER_DAY


def slice_window(rows: Sequence[CandleRow], start_ms: int, end_ms: int) -> list[CandleRow]:
    """Velas 15m con open_time en [start, end) — misma fuente para OLD y NEW."""
    out = [row for row in rows if start_ms <= row.open_time < end_ms]
    if not out:
        raise ValueError("ventana sin velas (FAIL CLOSED)")
    expected = expected_15m_candles(start_ms, end_ms)
    if len(out) != expected:
        raise ValueError(f"velas 15m en ventana {len(out)} != esperado {expected} (FAIL CLOSED)")
    for prev, cur in zip(out, out[1:], strict=False):
        if cur.open_time - prev.open_time != 900_000:
            raise ValueError("velas 15m no contiguas en la ventana (FAIL CLOSED)")
    return out


# --------------------------------------------------------------- hashing


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_hex(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def candle_sequence_hash(rows: Sequence[CandleRow]) -> str:
    return sha256_hex(
        [[r.open_time, r.close_time, r.open, r.high, r.low, r.close, r.volume] for r in rows]
    )


# --------------------------------------------------------------- señales


def signal_sequence(strategy: Strategy, candles: Sequence[Candle]) -> tuple[str, ...]:
    """Secuencia lógica canónica (una pasada, en el orden de las velas)."""
    out: list[str] = []
    for candle in candles:
        action = strategy.on_candle(candle).action
        out.append("HOLD" if action is Action.HOLD else str(action).upper())
    return tuple(out)


def signal_sequence_hash(sequence: Sequence[str]) -> str:
    return sha256_hex(list(sequence))


def _decision_to_signal(action: str | None) -> str:
    if action is None:
        return "HOLD"
    return action.upper()


class _RecordingProvider:
    """Envuelve el provider y registra la señal lógica por vela (paridad)."""

    def __init__(self, inner: StrategyDecisionProvider) -> None:
        self._inner = inner
        self.signals: list[str] = []

    def decide(self, **kwargs: Any) -> Any:
        decision = self._inner.decide(**kwargs)
        self.signals.append(_decision_to_signal(None if decision is None else decision.action))
        return decision


# --------------------------------------------------------------- modelos


def parity_scenario(strategy_version: str) -> ReplayScenario:
    """Escenario 22B explícito compartido con el modelo NEW (nunca defaults M7)."""
    return ReplayScenario(
        scenario_id=PARITY_SCENARIO_ID,
        risk=RiskConfig(stop_loss_required=True, version=RISK_VERSION),
        quantity=0.01,
        fee_rate=FEE_TAKER_BPS / 10_000.0,
        slippage_bps=SLIPPAGE_BPS,
        strategy_version=strategy_version,
        atr_period=ATR_PERIOD,
        sizing_mode="risk_engine",
        intensity=INTENSITY,
    )


@dataclass(frozen=True)
class ModelReport:
    """Resultado determinista y auditable de una corrida por modelo."""

    model: str
    strategy: str
    candles: int
    candle_hash: str
    signal_hash: str
    parity: str
    decisions: dict[str, int]
    fills: int
    exit_reasons_raw: dict[str, int]
    exit_reasons_presentation: dict[str, int]
    equity_final: float
    trace_hash: str
    extra: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "strategy": self.strategy,
            "candles": self.candles,
            "candle_hash": self.candle_hash,
            "signal_hash": self.signal_hash,
            "parity": self.parity,
            "decisions": self.decisions,
            "fills": self.fills,
            "exit_reasons_raw": self.exit_reasons_raw,
            "exit_reasons_presentation": self.exit_reasons_presentation,
            "equity_final": round(self.equity_final, 10),
            "trace_hash": self.trace_hash,
            "extra": self.extra,
        }


@dataclass(frozen=True)
class ModelRun:
    """Reporte + ledger económico (trades cerrados, orden cronológico) + stats."""

    report: ModelReport
    ledger: tuple[dict[str, Any], ...]
    stats: dict[str, int] = field(default_factory=dict)


def normalize_exit_reason(raw: str) -> str:
    """Mapeo SOLO para presentación; el raw se conserva aparte."""
    return EXIT_REASON_PRESENTATION.get(raw, raw)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"ledger: float esperado, recibido {value!r} (FAIL CLOSED)")
    return float(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"ledger: entero esperado, recibido {value!r} (FAIL CLOSED)")
    return value


def _as_str(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"ledger: cadena esperada, recibida {value!r} (FAIL CLOSED)")
    return value


def _ledger_row_old(
    *, entry: Fill, exit_fill: Fill, reason: str, strategy_version: str
) -> dict[str, Any]:
    """Fila del ledger económico OLD (PaperEngine close-only)."""
    quantity = exit_fill.quantity
    entry_ref = entry.price
    entry_exec = entry.exec_price
    exit_ref = exit_fill.price
    exit_exec = exit_fill.exec_price
    gross_exec = (exit_exec - entry_exec) * quantity
    fees = entry.fee + exit_fill.fee
    return {
        "record_type": "trade",
        "model": "old_close_only",
        "entry_timestamp": entry.timestamp_ms,
        "exit_timestamp": exit_fill.timestamp_ms,
        "entry_trigger_timestamp": entry.timestamp_ms,
        "exit_trigger_timestamp": exit_fill.timestamp_ms,
        "entry_reference_price": entry_ref,
        "entry_execution_price": entry_exec,
        "exit_reference_price": exit_ref,
        "exit_execution_price": exit_exec,
        "quantity": quantity,
        "exit_reason": reason,
        "exit_reason_presentation": normalize_exit_reason(reason),
        "gross_reference_pnl": (exit_ref - entry_ref) * quantity,
        "gross_execution_pnl": gross_exec,
        "fees": fees,
        "slippage": entry.slippage_cost + exit_fill.slippage_cost,
        "net_pnl": gross_exec - fees,
        "holding_ms": exit_fill.timestamp_ms - entry.timestamp_ms,
        "strategy_version": strategy_version,
        "risk_version": RISK_VERSION,
        "execution_model": OLD_EXECUTION_MODEL,
    }


def _ledger_row_new(record: Mapping[str, object]) -> dict[str, Any]:
    """Fila del ledger económico NEW (Trade-Level Replay), preservando el detalle."""
    quantity = _as_float(record["quantity"])
    entry_ref = _as_float(record["entry_reference_price"])
    entry_exec = _as_float(record["entry_execution_price"])
    exit_ref = _as_float(record["exit_reference_price"])
    exit_exec = _as_float(record["exit_execution_price"])
    fees = _as_float(record["fees"])
    reason = _as_str(record["exit_reason"])
    return {
        "record_type": "trade",
        "model": "trade_sequence",
        "entry_timestamp": _as_int(record["entry_fill_timestamp"]),
        "exit_timestamp": _as_int(record["exit_fill_timestamp"]),
        "entry_trigger_timestamp": _as_int(record["entry_trigger_timestamp"]),
        "exit_trigger_timestamp": _as_int(record["exit_trigger_timestamp"]),
        "entry_reference_price": entry_ref,
        "entry_execution_price": entry_exec,
        "exit_reference_price": exit_ref,
        "exit_execution_price": exit_exec,
        "quantity": quantity,
        "exit_reason": reason,
        "exit_reason_presentation": normalize_exit_reason(reason),
        "gross_reference_pnl": (exit_ref - entry_ref) * quantity,
        "gross_execution_pnl": (exit_exec - entry_exec) * quantity,
        "fees": fees,
        "slippage": _as_float(record["slippage"]),
        "net_pnl": _as_float(record["net_pnl"]),
        "holding_ms": _as_int(record["holding_ms"]),
        "mfe": _as_float(record["mfe"]),
        "mae": _as_float(record["mae"]),
        "stop": _as_float(record["initial_stop"]),
        "target": _as_float(record["initial_target"]),
        "strategy_version": _as_str(record["strategy_version"]),
        "risk_version": _as_str(record["risk_version"]),
        "execution_model": NEW_EXECUTION_MODEL,
        "execution_model_version": _as_str(record["execution_model_version"]),
    }


def run_old_close_only(
    *,
    strategy: Strategy,
    rows: Sequence[CandleRow],
    atr_values: Sequence[float | None],
    expected_signal_hash: str,
) -> ModelRun:
    """Semántica close-only previa: evalúa en el cierre de cada vela 15m."""
    engine = PaperEngine(
        config=RiskConfig(stop_loss_required=True, version=RISK_VERSION),
        fee_model=FeeModel(taker_bps=FEE_TAKER_BPS, maker_bps=FEE_TAKER_BPS),
        slippage_model=SlippageModel(bps=SLIPPAGE_BPS),
    )
    decisions = {"BUY": 0, "SELL": 0, "HOLD": 0}
    fills = 0
    raw_reasons: dict[str, int] = {}
    trace: list[list[Any]] = []
    signals: list[str] = []
    ledger: list[dict[str, Any]] = []
    entry_fill: Fill | None = None
    last_price = 0.0
    for index, row in enumerate(rows):
        last_price = row.close
        candle = Candle(
            timestamp_ms=row.open_time,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            turnover=0.0,
        )
        signal = strategy.on_candle(candle)
        action = "HOLD" if signal.action is Action.HOLD else str(signal.action).upper()
        signals.append(action)
        decision = TradingDecision(
            timestamp_ms=row.close_time,
            action=signal.action,
            confidence=1.0,
            intensity=Intensity.MEDIUM,
            rationale_summary=signal.reason,
        )
        event = engine.on_price(
            decision=decision,
            price=row.close,
            atr=atr_values[index],
            timestamp_ms=row.close_time,
        )
        decisions[event.action.name] = decisions.get(event.action.name, 0) + 1
        if event.filled:
            fills += 1
        if event.exit_reason:
            raw_reasons[event.exit_reason] = raw_reasons.get(event.exit_reason, 0) + 1
        fill = event.fill
        if event.filled and fill is not None:
            if event.action is Action.BUY:
                entry_fill = fill
            elif event.action is Action.SELL and event.exit_reason:
                if entry_fill is None:
                    raise ValueError("exit OLD sin entrada (FAIL CLOSED)")
                ledger.append(
                    _ledger_row_old(
                        entry=entry_fill,
                        exit_fill=fill,
                        reason=event.exit_reason,
                        strategy_version=strategy.version,
                    )
                )
                entry_fill = None
        trace.append(
            [
                row.close_time,
                event.action.name,
                event.filled,
                event.exit_reason,
                event.risk_reason,
                None if fill is None else round(fill.exec_price, 10),
                None if fill is None else round(fill.quantity, 10),
            ]
        )
    signal_hash = signal_sequence_hash(signals)
    report = ModelReport(
        model="old_close_only",
        strategy=strategy.version,
        candles=len(rows),
        candle_hash=candle_sequence_hash(rows),
        signal_hash=signal_hash,
        parity="PASS" if signal_hash == expected_signal_hash else "FAIL",
        decisions=decisions,
        fills=fills,
        exit_reasons_raw=dict(sorted(raw_reasons.items())),
        exit_reasons_presentation=dict(
            sorted((normalize_exit_reason(k), v) for k, v in raw_reasons.items())
        ),
        equity_final=engine.portfolio.equity(last_price),
        trace_hash=sha256_hex(trace),
        extra={
            "accounting": "paper-engine-close-only",
            "fee_bps": FEE_TAKER_BPS,
            "execution_model": OLD_EXECUTION_MODEL,
        },
    )
    return ModelRun(report=report, ledger=tuple(ledger))


def run_new_trade_sequence(
    *,
    strategy: Strategy,
    rows: Sequence[CandleRow],
    trades: Iterable[ReplayTrade],
    expected_signal_hash: str,
    dataset_id: str,
    dataset_sha: str,
) -> ModelRun:
    """Trade-Level Replay M7 con fills sobre trades históricos (proxy taker).

    `trades` se consume UNA sola vez: se pasa el iterable directo al motor, sin
    materializar la lista completa de trades Silver en memoria.
    """
    provider = _RecordingProvider(StrategyDecisionProvider(strategy=strategy, candle_rows=rows))
    scenario = parity_scenario(strategy.version)
    result: ReplayResult = replay_engine(
        rows,
        (),
        (),
        trades,
        scenario,
        provider,  # type: ignore[arg-type]
        dataset_id=dataset_id,
        dataset_sha=dataset_sha,
    )
    signal_hash = signal_sequence_hash(provider.signals)
    decisions = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for signal in provider.signals:
        decisions[signal] = decisions.get(signal, 0) + 1
    raw_reasons: dict[str, int] = {}
    trace: list[list[Any]] = []
    ledger: list[dict[str, Any]] = []
    net_total = 0.0
    for rec in result.records:
        reason = str(rec["exit_reason"])
        raw_reasons[reason] = raw_reasons.get(reason, 0) + 1
        net_total += float(rec["net_pnl"])  # type: ignore[arg-type]
        ledger.append(_ledger_row_new(rec))
        trace.append(
            [
                rec["entry_fill_timestamp"],
                rec["exit_fill_timestamp"],
                rec["exit_reason"],
                round(float(rec["entry_execution_price"]), 10),  # type: ignore[arg-type]
                round(float(rec["quantity"]), 10),  # type: ignore[arg-type]
                round(float(rec["net_pnl"]), 10),  # type: ignore[arg-type]
            ]
        )
    report = ModelReport(
        model="trade_sequence",
        strategy=strategy.version,
        candles=len(rows),
        candle_hash=candle_sequence_hash(rows),
        signal_hash=signal_hash,
        parity="PASS" if signal_hash == expected_signal_hash else "FAIL",
        decisions=decisions,
        fills=int(result.stats["decisions_filled"]),
        exit_reasons_raw=dict(sorted(raw_reasons.items())),
        exit_reasons_presentation=dict(
            sorted((normalize_exit_reason(k), v) for k, v in raw_reasons.items())
        ),
        equity_final=scenario.risk.capital + net_total,
        trace_hash=sha256_hex(trace),
        extra={
            "execution_model": NEW_EXECUTION_MODEL,
            "decisions_rejected": int(result.stats.get("decisions_rejected", 0)),
            "rejected_reasons": dict(sorted(result.rejected_reasons.items())),
        },
    )
    return ModelRun(report=report, ledger=tuple(ledger), stats=dict(result.stats))


# --------------------------------------------------------------- summary


def _iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def summary_identities(
    *,
    model: str,
    strategy: str,
    report: ModelReport,
    dataset_id: str,
    dataset_sha: str,
    start_ms: int,
    end_ms: int,
    code_git_sha: str,
) -> dict[str, Any]:
    """Identidades de una corrida (mismas claves OLD/NEW para comparabilidad)."""
    del strategy  # el alias corto ya vive en `model`/`report`; no se duplica.
    scenario = parity_scenario(report.strategy)
    execution_model = report.extra.get("execution_model")
    if not isinstance(execution_model, str):
        execution_model = NEW_EXECUTION_MODEL if model == "trade_sequence" else OLD_EXECUTION_MODEL
    return {
        "code_git_sha": code_git_sha,
        "dataset_id": dataset_id,
        "dataset_sha": dataset_sha,
        "common_window_start": _iso_ms(start_ms),
        "common_window_end_exclusive": _iso_ms(end_ms),
        "candle_hash": report.candle_hash,
        "signal_hash": report.signal_hash,
        "strategy_version": report.strategy,
        "risk_version": RISK_VERSION,
        "execution_model": execution_model,
        "fee_bps": FEE_TAKER_BPS,
        "slippage_bps": SLIPPAGE_BPS,
        "stop_atr": scenario.risk.stop_atr_multiplier,
        "target_r": scenario.risk.take_profit_r_multiple,
        "trailing_atr": scenario.risk.trailing_atr_multiplier,
    }


def summarize_ledger(ledger: Sequence[Mapping[str, Any]], *, capital: float) -> dict[str, Any]:
    """Métricas económicas con definición única para OLD y NEW.

    - `net_pnl` realizado = suma de `net_pnl` de trades cerrados.
    - `profit_factor` = sum(net>0) / |sum(net<0)|; `None` si no hay pérdidas.
    - `win_rate` = trades con `net_pnl > 0` / trades cerrados.
    - `final_equity` = capital + net realizado (REALIZED-ONLY, no mark-to-market).
    - `max_drawdown_*` sobre la curva de equity realizada ordenada por cierre.
    """
    rows = list(ledger)
    closed = len(rows)
    nets = [_as_float(row["net_pnl"]) for row in rows]
    net_total = sum(nets)
    wins = [n for n in nets if n > 0.0]
    losses = [n for n in nets if n < 0.0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor: float | None = gross_profit / gross_loss if gross_loss > 0.0 else None
    raw_counts = Counter(_as_str(row["exit_reason"]) for row in rows)
    presentation_counts = Counter(_as_str(row["exit_reason_presentation"]) for row in rows)
    holdings = [_as_float(row["holding_ms"]) for row in rows]

    equity = float(capital)
    peak = float(capital)
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    for row in sorted(rows, key=lambda r: _as_int(r["exit_timestamp"])):
        equity += _as_float(row["net_pnl"])
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_dd_abs:
            max_dd_abs = drawdown
        if peak > 0.0:
            drawdown_pct = drawdown / peak
            if drawdown_pct > max_dd_pct:
                max_dd_pct = drawdown_pct

    return {
        "closed_trades": closed,
        "gross_reference_pnl": sum(
            _as_float(row["gross_reference_pnl"])
            for row in rows
            if row.get("gross_reference_pnl") is not None
        ),
        "gross_execution_pnl": sum(
            _as_float(row["gross_execution_pnl"])
            for row in rows
            if row.get("gross_execution_pnl") is not None
        ),
        "fees": sum(_as_float(row["fees"]) for row in rows),
        "slippage": sum(_as_float(row["slippage"]) for row in rows),
        "net_pnl": net_total,
        "expectancy": net_total / closed if closed else 0.0,
        "profit_factor": profit_factor,
        "win_rate": len(wins) / closed if closed else 0.0,
        "average_holding_ms": (sum(holdings) / closed) if closed else 0.0,
        "exit_reason_counts_raw": dict(sorted(raw_counts.items())),
        "exit_reason_counts_presentation": dict(sorted(presentation_counts.items())),
        "final_equity": float(capital) + net_total,
        "max_drawdown_abs": max_dd_abs,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_basis": MAX_DRAWDOWN_BASIS,
        "profit_factor_basis": PROFIT_FACTOR_BASIS,
    }


def ledger_jsonl_bytes(ledger: Sequence[Mapping[str, Any]]) -> bytes:
    """JSONL determinista del ledger (una línea por trade cerrado)."""
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
        for row in ledger
    )


def summary_json_bytes(summary: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def build_summary(
    *,
    model: str,
    strategy: str,
    ledger: Sequence[Mapping[str, Any]],
    ledger_bytes: bytes,
    identities: Mapping[str, Any],
    capital: float,
) -> dict[str, Any]:
    """Summary determinista: identidades + métricas + hashes del ledger."""
    payload: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "model": model,
        "strategy": strategy,
        **identities,
        "metrics": summarize_ledger(ledger, capital=capital),
        "max_drawdown_basis": MAX_DRAWDOWN_BASIS,
        "trade_ledger_sha256": sha256_bytes(ledger_bytes),
        "trade_ledger_bytes": len(ledger_bytes),
        "trade_ledger_records": len(ledger),
    }
    payload["summary_sha256"] = sha256_hex(payload)
    return payload


# --------------------------------------------------------------- artefactos


@dataclass(frozen=True)
class ArtifactPaths:
    summary: Path
    trades: Path


def artifact_paths(output_dir: Path, *, strategy: str, model: str) -> ArtifactPaths:
    base = f"{strategy}-{model}"
    return ArtifactPaths(
        summary=output_dir / f"{base}-summary.json",
        trades=output_dir / f"{base}-trades.jsonl",
    )


def write_artifact(path: Path, payload: bytes) -> str:
    """Escritura atómica idempotente: created | skipped | FAIL CLOSED.

    Patrón `.part → verify (round-trip) → rename(2)`; mismo contenido ⇒ SKIP;
    contenido distinto ⇒ `ArtifactConflictError`.
    """
    if path.exists():
        if path.read_bytes() == payload:
            return "skipped"
        raise ArtifactConflictError(
            f"artefacto existente con contenido distinto: {path} (FAIL CLOSED)"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(payload)
    if part.read_bytes() != payload:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"round-trip del artefacto fallido: {path} (FAIL CLOSED)")
    os.replace(part, path)
    return "created"


def write_run_artifacts(
    *,
    output_dir: Path,
    strategy: str,
    model: str,
    run: ModelRun,
    identities: Mapping[str, Any],
    capital: float,
) -> dict[str, Any]:
    """Genera summary + trades.jsonl de forma atómica y determinista."""
    paths = artifact_paths(output_dir, strategy=strategy, model=model)
    ledger_bytes = ledger_jsonl_bytes(run.ledger)
    summary = build_summary(
        model=model,
        strategy=strategy,
        ledger=run.ledger,
        ledger_bytes=ledger_bytes,
        identities=identities,
        capital=capital,
    )
    trades_status = write_artifact(paths.trades, ledger_bytes)
    summary_status = write_artifact(paths.summary, summary_json_bytes(summary))
    return {
        "model": model,
        "strategy": strategy,
        "summary_path": str(paths.summary),
        "trades_path": str(paths.trades),
        "summary_status": summary_status,
        "trades_status": trades_status,
        "summary_sha256": summary["summary_sha256"],
        "trade_ledger_sha256": summary["trade_ledger_sha256"],
        "closed_trades": summary["metrics"]["closed_trades"],
        "max_drawdown_basis": MAX_DRAWDOWN_BASIS,
    }


# --------------------------------------------------------------- CLI


def resolve_code_git_sha(repo_root: Path | None = None) -> str:
    """SHA de git del árbol de código; `unknown` si no hay repo (sin romper)."""
    root = repo_root if repo_root is not None else _REPO_ROOT
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return DEFAULT_CODE_GIT_SHA
    sha = completed.stdout.strip()
    if completed.returncode == 0 and sha:
        return sha
    return DEFAULT_CODE_GIT_SHA


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M9-B2B common window runner (OLD vs NEW)")
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--trades-dir", required=True, type=Path)
    parser.add_argument("--candles-dir", required=True, type=Path)
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--start", default=COMMON_WINDOW_START.isoformat())
    parser.add_argument("--end-exclusive", default=COMMON_WINDOW_END_EXCLUSIVE.isoformat())
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--code-git-sha", default=None)
    parser.add_argument("--expect-common-window", action="store_true")
    parser.add_argument("--require-marker", type=Path, default=None)
    return parser


def _resolve_window(args: argparse.Namespace) -> tuple[int, int]:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end_exclusive)
    start_ms = day_start_ms(start)
    end_ms = day_start_ms(end)
    if args.expect_common_window:
        expected_start, expected_end = common_window_bounds()
        if (start_ms, end_ms) != (expected_start, expected_end):
            raise ValueError("ventana != COMMON_WINDOW (FAIL CLOSED)")
        if window_days(start_ms, end_ms) != COMMON_WINDOW_DAYS:
            raise ValueError("días != 647 (FAIL CLOSED)")
        if expected_15m_candles(start_ms, end_ms) != EXPECTED_15M_CANDLES:
            raise ValueError("velas esperadas != 62112 (FAIL CLOSED)")
    return start_ms, end_ms


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.require_marker is not None:
        ensure_marker(args.require_marker)
    start_ms, end_ms = _resolve_window(args)
    dataset = validate_dataset(args.dataset_dir, args.trades_dir, args.candles_dir)
    all_rows = load_candles(dataset, ("15m",))["15m"]
    rows = slice_window(all_rows, start_ms, end_ms)
    domain_candles = rows_to_domain_candles(rows)
    atr_values = atr_series(domain_candles, period=ATR_PERIOD)
    build_name = _STRATEGY_BUILD_NAME[args.strategy]
    # Las estrategias son stateful (single-use): una instancia para el hash
    # canónico y otra fresca para el modelo, ambas sobre las MISMAS velas.
    expected_hash = signal_sequence_hash(
        signal_sequence(replay_cli._build_strategy(build_name, domain_candles), domain_candles)
    )
    strategy = replay_cli._build_strategy(build_name, domain_candles)

    if args.model == "old_close_only":
        run = run_old_close_only(
            strategy=strategy,
            rows=rows,
            atr_values=atr_values,
            expected_signal_hash=expected_hash,
        )
    else:
        # Streaming: el generador se pasa directo al motor (nunca `list(...)`).
        run = run_new_trade_sequence(
            strategy=strategy,
            rows=rows,
            trades=_window_trades(dataset, start_ms, end_ms),
            expected_signal_hash=expected_hash,
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
        )
    report = run.report

    days = window_days(start_ms, end_ms)
    print(
        f"WINDOW start_ms={start_ms} end_exclusive_ms={end_ms} days={days} "
        f"expected_15m_candles={expected_15m_candles(start_ms, end_ms)}"
    )
    print(
        f"DATASET id={dataset.dataset_id} sha={dataset.dataset_sha} "
        f"dates={dataset.dates[0]}..{dataset.dates[-1]} fidelity={dataset.ordering_fidelity}"
    )
    print(
        f"MODEL {report.model} strategy={args.strategy} candles={report.candles} "
        f"candle_hash={report.candle_hash}"
    )
    print(f"PARITY {report.parity} signal_hash={report.signal_hash} expected={expected_hash}")
    print(
        f"SUMMARY decisions={json.dumps(report.decisions, sort_keys=True)} "
        f"fills={report.fills} "
        f"exit_raw={json.dumps(report.exit_reasons_raw, sort_keys=True)} "
        f"exit_presentation={json.dumps(report.exit_reasons_presentation, sort_keys=True)} "
        f"equity_final={report.equity_final}"
    )
    print(f"EXTRA {json.dumps(report.extra, sort_keys=True)}")
    print(f"REPORT_SHA256 {sha256_hex(report.as_payload())}")

    if args.output_dir is not None:
        identities = summary_identities(
            model=args.model,
            strategy=args.strategy,
            report=report,
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
            start_ms=start_ms,
            end_ms=end_ms,
            code_git_sha=args.code_git_sha or resolve_code_git_sha(),
        )
        artifacts = write_run_artifacts(
            output_dir=args.output_dir,
            strategy=args.strategy,
            model=args.model,
            run=run,
            identities=identities,
            capital=parity_scenario(report.strategy).risk.capital,
        )
        print(f"ARTIFACT {json.dumps(artifacts, sort_keys=True)}")

    if report.parity != "PASS":
        print("PARITY_FAILED=1", file=sys.stderr)
        return 1
    return 0


def _window_trades(dataset: Any, start_ms: int, end_ms: int) -> Iterable[ReplayTrade]:
    from infrastructure.medallion.replay import iter_trades

    for trade in iter_trades(dataset):
        if trade.ts < start_ms:
            continue
        if trade.ts >= end_ms:
            break
        yield trade


if __name__ == "__main__":
    raise SystemExit(main())
