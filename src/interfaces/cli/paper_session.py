"""Subcomando `paper-session` — sesión de paper trading evaluada (PRD §15, §25).

Ejecuta una sesión de paper trading determinista sobre el dataset congelado: cada
decisión pasa por el Risk Engine y se liquida con fees/slippage reales; al cierre se
evalúan las métricas §45 con coste LLM explícito (0.0 — fuente de decisiones
determinista sin llamadas LLM) y benchmark Buy & Hold. Verifica el SHA-256 del
manifest ANTES de correr; salida JSON byte-idéntica ante el mismo input.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from application.ports.dataset_store import DatasetStore
from application.services.paper_engine import PaperEngine
from domain.evaluation.buy_hold import run_buy_and_hold
from domain.evaluation.metrics import compute_metrics
from domain.market.candle import Timeframe
from domain.market.indicators import atr
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.fees import FeeModel
from domain.trading.fill import FillModel
from domain.trading.signal import Intensity
from domain.trading.slippage import SlippageModel
from domain.trading.strategy import EmaRsiBaseline
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.download import verify_manifest

DEFAULT_DATASET = "BYBIT_ETHBTC_V001"
MINUTES_PER_YEAR = 366 * 24 * 60


def _periods_per_year(timeframe: Timeframe) -> float:
    return MINUTES_PER_YEAR / float(timeframe.minutes)


def run_paper_session(
    store: DatasetStore,
    manifest_path: Path,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="paper-session")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--confidence", type=float, default=0.8)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    try:
        timeframe = Timeframe.from_label(args.timeframe)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        verified = verify_manifest(store, manifest_path) == 0
    except (KeyError, OSError, ValueError):
        verified = False
    if not verified:
        print("ERROR: dataset congelado no verificado; sesión paper abortada")
        return 1

    manifest = store.read_manifest(manifest_path)
    entry = next(
        (f for f in manifest.files if f.symbol == args.symbol and f.timeframe == timeframe.label),
        None,
    )
    if entry is None:
        print(f"ERROR: {args.symbol} {timeframe.label} ausente del dataset congelado")
        return 2

    candles = store.read_candles(Path(entry.path))
    atr_series = atr(candles)
    risk_config = RiskConfig()
    fee_model = FeeModel()
    slippage_model = SlippageModel()
    paper = PaperEngine(
        config=risk_config,
        fee_model=fee_model,
        slippage_model=slippage_model,
    )
    strategy = EmaRsiBaseline()
    periods_per_year = _periods_per_year(timeframe)

    decisions = {"buy": 0, "sell": 0, "hold": 0}
    filled = 0
    rejected = 0
    open_bars = 0
    equity: list[float] = []

    for i, candle in enumerate(candles):
        signal = strategy.on_candle(candle)
        decisions[signal.action.value] += 1
        decision = TradingDecision(
            timestamp_ms=candle.timestamp_ms,
            action=signal.action,
            confidence=args.confidence,
            intensity=Intensity.MEDIUM,
            rationale_summary=signal.reason,
        )
        event = paper.on_price(
            decision=decision,
            price=candle.close,
            atr=atr_series[i],
            timestamp_ms=candle.timestamp_ms,
        )
        if event.fill is not None:
            filled += 1
        elif event.risk_reason:
            rejected += 1
        if paper.position is not None:
            open_bars += 1
        equity.append(paper.mark_to_market(price=candle.close))

    closed_trades = paper.portfolio.trades
    exposure = open_bars / len(candles) if candles else 0.0
    metrics = compute_metrics(
        closed_trades,
        equity,
        periods_per_year=periods_per_year,
        llm_cost=0.0,
        exposure=exposure,
    )
    benchmark = run_buy_and_hold(
        candles,
        fill_model=FillModel(fee_model=fee_model, slippage_model=slippage_model),
        initial_cash=risk_config.capital,
        periods_per_year=periods_per_year,
    )

    kill_switch_active = paper.kill_switch_state.active
    payload_session = {
        "symbol": args.symbol,
        "timeframe": timeframe.label,
        "bars": len(candles),
        "decisions": decisions,
        "filled": filled,
        "rejected": rejected,
        "kill_switch_tripped": kill_switch_active,
    }
    payload = {
        "experiment_id": (
            f"paper-session-{manifest.dataset_version}-"
            f"{strategy.version}-{args.symbol}-{timeframe.label}"
        ).lower(),
        "dataset": {
            "version": manifest.dataset_version,
            "file": entry.path,
            "sha256": entry.sha256,
            "rows": entry.row_count,
        },
        "decision_source": {
            "type": "deterministic-baseline",
            "strategy_version": strategy.version,
            "confidence": args.confidence,
            "llm_calls": 0,
            "note": "sin proveedor LLM en sesión local; llm_cost=0.0 explícito",
        },
        "risk_config": dataclasses.asdict(risk_config),
        "session": payload_session,
        "metrics": dataclasses.asdict(metrics),
        "benchmark_buy_hold": {
            "strategy_version": "buy-and-hold",
            "metrics": dataclasses.asdict(benchmark),
        },
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"experiment_id={payload['experiment_id']}")
    print(
        f"bars={len(candles)} buy={decisions['buy']} sell={decisions['sell']} "
        f"filled={filled} rejected={rejected}"
    )
    print(
        f"net_pnl={metrics.net_pnl:.6f} fully_loaded={metrics.fully_loaded_pnl:.6f} "
        f"fees={metrics.fees:.6f} slippage={metrics.slippage:.6f} llm_cost={metrics.llm_cost:.6f} "
        f"trades={metrics.trades} kill_switch={kill_switch_active}"
    )
    return 0


def paper_session(argv: list[str] | None) -> int:
    local_argv = list(argv if argv is not None else [])
    parser = argparse.ArgumentParser(prog="paper-session", add_help=False)
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    known, rest = parser.parse_known_args(local_argv)
    manifest_path = Path("docs") / "datasets" / f"{known.dataset_version}.manifest.json"
    return run_paper_session(LocalDatasetStore(), manifest_path, rest or None)
