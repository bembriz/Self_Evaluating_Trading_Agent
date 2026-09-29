#!/usr/bin/env python3
"""M9-B2A — Runner de ventana común OLD (close-only) vs NEW (trade-sequence).

Orquesta la comparación de 647 días sobre el **mismo** Gold Medallion: OLD y NEW
consumen exactamente la misma secuencia de velas 15m y las mismas estrategias;
el runner no define reglas de trading (estrategia, RiskEngine, fills, fees,
slippage y portfolio accounting provienen del runtime existente).

- OLD = `old_close_only`: PaperEngine real con semántica close-only (precio =
  candle.close, ATR = ATR de la vela confirmada) + RiskEngine dinámico.
- NEW = `trade_sequence`: Trade-Level Replay M7 (TRADE_SEQUENCE_TAKER_PROXY),
  fills sobre los trades históricos de Silver.

Paridad de señales obligatoria antes de cualquier lectura económica: ambos
modelos deben reproducir la misma secuencia BUY/SELL/HOLD de 62112 velas.

Uso:
  python3 harness/scripts/m9b_common_window.py \\
      --dataset-dir <Gold replay dataset> --trades-dir <Silver trades> \\
      --candles-dir <Silver candles> --strategy baseline \\
      --model old_close_only [--start 2023-09-09] [--end-exclusive 2025-06-17] \\
      [--expect-common-window] [--require-marker /srv/data/.lenovosrv-data-volume]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
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


def normalize_exit_reason(raw: str) -> str:
    """Mapeo SOLO para presentación; el raw se conserva aparte."""
    return EXIT_REASON_PRESENTATION.get(raw, raw)


def run_old_close_only(
    *,
    strategy: Strategy,
    rows: Sequence[CandleRow],
    atr_values: Sequence[float | None],
    expected_signal_hash: str,
) -> ModelReport:
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
    return ModelReport(
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
        extra={"accounting": "paper-engine-close-only", "fee_bps": FEE_TAKER_BPS},
    )


def run_new_trade_sequence(
    *,
    strategy: Strategy,
    rows: Sequence[CandleRow],
    trades: Sequence[ReplayTrade],
    expected_signal_hash: str,
    dataset_id: str,
    dataset_sha: str,
) -> tuple[ModelReport, ReplayResult]:
    """Trade-Level Replay M7 con fills sobre trades históricos (proxy taker)."""
    provider = _RecordingProvider(
        StrategyDecisionProvider(strategy=strategy, candle_rows=list(rows))
    )
    scenario = parity_scenario(strategy.version)
    result = replay_engine(
        list(rows),
        (),
        (),
        list(trades),
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
    net_total = 0.0
    for rec in result.records:
        reason = str(rec["exit_reason"])
        raw_reasons[reason] = raw_reasons.get(reason, 0) + 1
        net_total += float(rec["net_pnl"])  # type: ignore[arg-type]
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
    return (
        ModelReport(
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
                "execution_model": "TRADE_SEQUENCE_TAKER_PROXY",
                "decisions_rejected": int(result.stats.get("decisions_rejected", 0)),
                "rejected_reasons": dict(sorted(result.rejected_reasons.items())),
            },
        ),
        result,
    )


# --------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M9-B2A common window runner (OLD vs NEW)")
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--trades-dir", required=True, type=Path)
    parser.add_argument("--candles-dir", required=True, type=Path)
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--start", default=COMMON_WINDOW_START.isoformat())
    parser.add_argument("--end-exclusive", default=COMMON_WINDOW_END_EXCLUSIVE.isoformat())
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
        report = run_old_close_only(
            strategy=strategy,
            rows=rows,
            atr_values=atr_values,
            expected_signal_hash=expected_hash,
        )
    else:
        trades = list(_window_trades(dataset, start_ms, end_ms))
        report, _ = run_new_trade_sequence(
            strategy=strategy,
            rows=rows,
            trades=trades,
            expected_signal_hash=expected_hash,
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
        )

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
