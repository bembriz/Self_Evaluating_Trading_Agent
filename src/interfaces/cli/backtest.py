"""Subcomando `backtest` — corrida oficial sobre dataset congelado (PRD §29, §40–45).

Verifica el SHA-256 del manifest ANTES de correr (invariante del dataset congelado),
ejecuta el baseline determinista `EmaRsiBaseline` con fees + slippage reales y
persiste trades/métricas §45 + benchmark Buy & Hold en JSON determinista:
mismo input ⇒ mismos bytes de salida.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from application.ports.dataset_store import DatasetStore
from application.services.backtest_engine import BacktestEngine
from domain.evaluation.buy_hold import run_buy_and_hold
from domain.market.candle import Timeframe
from domain.trading.fees import FeeModel
from domain.trading.fill import FillModel
from domain.trading.slippage import SlippageModel
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.download import verify_manifest

DEFAULT_DATASET = "BYBIT_ETHBTC_V001"
MINUTES_PER_YEAR = 366 * 24 * 60


def _periods_per_year(timeframe: Timeframe) -> float:
    return MINUTES_PER_YEAR / float(timeframe.minutes)


def run_backtest(
    store: DatasetStore,
    manifest_path: Path,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="backtest")
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--initial-cash", type=float, default=1000.0)
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
        print("ERROR: dataset congelado no verificado; corrida abortada")
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
    fee_model = FeeModel()
    slippage_model = SlippageModel()
    fill_model = FillModel(fee_model=fee_model, slippage_model=slippage_model)
    config = EmaRsiConfig()
    strategy = EmaRsiBaseline(config=config)
    periods_per_year = _periods_per_year(timeframe)
    engine = BacktestEngine(
        strategy=strategy,
        fill_model=fill_model,
        initial_cash=args.initial_cash,
        periods_per_year=periods_per_year,
    )
    result = engine.run(candles)
    benchmark = run_buy_and_hold(
        candles,
        fill_model=fill_model,
        initial_cash=args.initial_cash,
        periods_per_year=periods_per_year,
    )

    payload = {
        "experiment_id": (
            f"backtest-{manifest.dataset_version}-"
            f"{strategy.version}-{args.symbol}-{timeframe.label}"
        ).lower(),
        "dataset": {
            "version": manifest.dataset_version,
            "file": entry.path,
            "sha256": entry.sha256,
            "rows": entry.row_count,
        },
        "strategy": {
            "name": type(strategy).__name__,
            "version": strategy.version,
            "config": dataclasses.asdict(config),
        },
        "params": {
            "symbol": args.symbol,
            "timeframe": timeframe.label,
            "initial_cash": args.initial_cash,
            "periods_per_year": periods_per_year,
            "fee_model": dataclasses.asdict(fee_model),
            "slippage_model": dataclasses.asdict(slippage_model),
        },
        "signals": result.signals,
        "metrics": dataclasses.asdict(result.metrics),
        "benchmark_buy_hold": {
            "strategy_version": "buy-and-hold",
            "metrics": dataclasses.asdict(benchmark),
        },
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    metrics = result.metrics
    print(f"experiment_id={payload['experiment_id']}")
    print(
        f"net_pnl={metrics.net_pnl:.6f} fully_loaded={metrics.fully_loaded_pnl:.6f} "
        f"trades={metrics.trades} win_rate={metrics.win_rate} "
        f"profit_factor={metrics.profit_factor} sharpe={metrics.sharpe} "
        f"max_drawdown={metrics.max_drawdown:.6f}"
    )
    print(
        f"buy_hold: net_pnl={benchmark.net_pnl:.6f} sharpe={benchmark.sharpe} "
        f"max_drawdown={benchmark.max_drawdown:.6f}"
    )
    return 0


def backtest(argv: list[str] | None) -> int:
    local_argv = list(argv if argv is not None else [])
    parser = argparse.ArgumentParser(prog="backtest", add_help=False)
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    known, rest = parser.parse_known_args(local_argv)
    manifest_path = Path("docs") / "datasets" / f"{known.dataset_version}.manifest.json"
    return run_backtest(LocalDatasetStore(), manifest_path, rest or None)
