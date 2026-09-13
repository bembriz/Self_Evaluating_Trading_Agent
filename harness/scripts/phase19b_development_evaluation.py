#!/usr/bin/env python3
"""Phase 19B — DEVELOPMENT economic evaluation: baseline-v1 vs EthDonchianBreakout-v1.

Runs both strategies over DEVELOPMENT [0, 62208) with the real
FrozenDatasetAdapter + LabSessionRunner + PaperEngine + RiskEngine, persists both
experiments via ExperimentRegistry and writes the comparison evidence.

Adds signal/execution attribution, ADX/breakout diagnostics and trade-structure
metrics. Never touches WALK_FORWARD [62208, 88128) nor FINAL_HOLDOUT
[88128, 103680). Reuses the pure helpers from `lab.development_evaluation`
(Phase 18B); no historical 18B/18D artifact is modified.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from application.services.paper_engine import PaperEngine
from domain.market.candle import Candle
from domain.market.indicators import adx
from domain.risk.config import RiskConfig
from domain.trading.signal import Action, Signal
from domain.trading.strategy import EmaRsiBaseline
from lab.development_evaluation import (
    MAX_DRAWDOWN_MATERIAL_ABS,
    classify_development_result,
    compare_metrics,
    count_signals,
    session_metrics,
)
from lab.experiment_spec import ExperimentRun, ExperimentSpec
from lab.fingerprints import (
    ImportlibSourceResolver,
    StrategyDefinition,
    strategy_artifact_identity,
)
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.kernel_bundle import KernelIdentity, make_kernel_identity, real_strategy_contract_source
from lab.registry import ExperimentRegistry, compare_runs
from lab.session_runner import LabSessionResult, LabSessionRunner
from lab.splits import (
    DATASET_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    WALK_FORWARD_END,
    WALK_FORWARD_START,
    is_holdout_range,
)
from lab.strategies.eth_donchian_breakout import (
    EthDonchianBreakout,
)
from lab.strategies.eth_donchian_breakout import (
    strategy_definition as donchian_definition,
)
from lab.walk_forward import trades_from_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_SYMBOL = "ETHUSDT"
TIMEFRAME = "15m"
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
DEFAULT_ROW_START = DEVELOPMENT_START
DEFAULT_ROW_END = DEVELOPMENT_END
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "phases" / "19B" / "evidence"
RUN_1_CREATED_AT = "2026-09-13T00:00:00+00:00"
RUN_2_CREATED_AT = "2026-09-13T00:00:01+00:00"

METRIC_ROWS: tuple[tuple[str, str], ...] = (
    ("signals_buy", "signals_buy"),
    ("signals_sell", "signals_sell"),
    ("signals_hold", "signals_hold"),
    ("fills", "fills"),
    ("closed_trades", "closed_trades"),
    ("net_pnl", "net_pnl"),
    ("return_pct", "return_pct"),
    ("fees", "fees"),
    ("slippage", "slippage"),
    ("max_drawdown", "max_drawdown"),
    ("profit_factor", "profit_factor"),
    ("expectancy", "expectancy"),
    ("win_rate", "win_rate"),
    ("average_win", "average_win"),
    ("average_loss", "average_loss"),
)


def _git_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _baseline_definition() -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="ema-rsi-baseline",
        strategy_version="baseline-v1",
        kind="deterministic",
        normalized_config={"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_exit": 80.0},
        sources=("domain.trading.strategy",),
    )


def _dataset(row_start: int, row_end: int) -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "symbol": PRIMARY_SYMBOL,
        "timeframe": TIMEFRAME,
        "row_start": row_start,
        "row_end": row_end,
    }


def _build_spec(
    *,
    dataset: Mapping[str, Any],
    name: str,
    version: str,
    artifact_identity: str,
    kernel: KernelIdentity,
) -> ExperimentSpec:
    return ExperimentSpec(
        dataset=dataset,
        strategy={"name": name, "version": version, "artifact_identity": artifact_identity},
        risk={"version": ENGINE_CONFIG.version, "capital": ENGINE_CONFIG.capital},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={
            "kernel_bundle_version": kernel.kernel_bundle_version,
            "kernel_fingerprint": kernel.kernel_fingerprint,
        },
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "N/A"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return f"{value:.6f}"
    return str(value)


def _delta_value(base: Any, candidate: Any) -> float | None:
    if not isinstance(base, (int, float)) or not isinstance(candidate, (int, float)):
        return None
    if isinstance(base, bool) or isinstance(candidate, bool):
        return None
    if isinstance(base, float) and not math.isfinite(base):
        return None
    if isinstance(candidate, float) and not math.isfinite(candidate):
        return None
    return float(candidate) - float(base)


def trade_structure(result: LabSessionResult) -> dict[str, Any]:
    """Trade-structure metrics derived from the existing fill trace (no new framework)."""
    trades = trades_from_trace(result.events)
    durations = [trade.exit_ts - trade.entry_ts for trade in trades]
    net = [trade.net_pnl for trade in trades]
    return {
        "average_holding_duration_ms": statistics.mean(durations) if durations else None,
        "median_holding_duration_ms": statistics.median(durations) if durations else None,
        "average_trade_pnl": statistics.mean(net) if net else None,
        "largest_win": max(net) if net else None,
        "largest_loss": min(net) if net else None,
    }


def execution_attribution(
    donchian_signals: Sequence[Signal], result: LabSessionResult
) -> dict[str, Any]:
    """Separate strategy signals from fills and RiskEngine rejections."""
    buy_signals = sum(signal.action is Action.BUY for signal in donchian_signals)
    sell_signals = sum(signal.action is Action.SELL for signal in donchian_signals)
    executed_buys = sum(event.filled and event.action == "BUY" for event in result.events)
    executed_sells = sum(event.filled and event.action == "SELL" for event in result.events)
    rejected_buys = sum(not event.filled and event.action == "BUY" for event in result.events)
    sell_without_position = sum(
        not event.filled and event.action == "SELL" and event.risk_reason == "no_position_to_reduce"
        for event in result.events
    )
    return {
        "DONCHIAN_BUY_SIGNALS": buy_signals,
        "DONCHIAN_SELL_SIGNALS": sell_signals,
        "EXECUTED_BUYS": executed_buys,
        "EXECUTED_SELLS": executed_sells,
        "REJECTED_BUYS": rejected_buys,
        "SELL_SIGNALS_WITHOUT_POSITION": sell_without_position,
        "SUPERSEDED_BUYS": buy_signals - executed_buys - rejected_buys,
    }


def breakout_diagnostics(
    candles: Sequence[Candle], *, lookback: int = 20, adx_min: float = 20.0
) -> dict[str, int]:
    """Descriptive ADX/breakout accounting (raw = confirmed + blocked)."""
    adx_values = adx(candles, 14)
    highs = [candle.high for candle in candles]
    raw = confirmed = blocked = 0
    for index in range(lookback, len(candles)):
        prior_high = max(highs[index - lookback : index])
        if candles[index].close > prior_high:
            raw += 1
            value = adx_values[index]
            if value is not None and value > adx_min:
                confirmed += 1
            else:
                blocked += 1
    return {
        "RAW_BREAKOUT_EVENTS": raw,
        "BREAKOUTS_CONFIRMED_BY_ADX": confirmed,
        "BREAKOUTS_BLOCKED_BY_ADX": blocked,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the 2-way comparison + attribution + diagnostics + trade structure."""
    baseline = report["BASELINE"]
    donchian = report["DONCHIAN"]
    primary = report["PRIMARY_DELTAS"]
    attribution = report["SIGNAL_EXECUTION_ATTRIBUTION"]
    diagnostics = report["ADX_BREAKOUT_DIAGNOSTICS"]
    base_structure = report["TRADE_STRUCTURE"]["baseline-v1"]
    donchian_structure = report["TRADE_STRUCTURE"]["EthDonchianBreakout-v1"]
    lines = [
        "# Phase 19B — DEVELOPMENT Economic Evaluation (baseline vs Donchian)",
        "",
        f"- A baseline-v1: `{report['BASELINE_SPEC_ID']}`",
        f"- B EthDonchianBreakout-v1: `{report['DONCHIAN_SPEC_ID']}`",
        f"- Slice: DEVELOPMENT `[{report['ROW_START']}, {report['ROW_END']})`",
        f"- SpecIds differ: `{report['SPEC_IDS_DIFFERENT']}`",
        f"- Reproducibility: `{report['REPRODUCIBILITY']}`",
        f"- Development result: `{report['DEVELOPMENT_RESULT']}`",
        f"- Walk-forward candidate: `{report['WALK_FORWARD_CANDIDATE']}`",
        f"- Edge present: `{report['EDGE_PRESENT']}`",
        f"- Strategy promotable: `{report['STRATEGY_PROMOTABLE']}`",
        "",
        "| Metric | baseline-v1 | EthDonchianBreakout-v1 | Delta |",
        "|---|---|---|---|",
    ]
    for key, label in METRIC_ROWS:
        lines.append(
            f"| {label} | {_fmt(baseline[key])} | {_fmt(donchian[key])} | "
            f"{_fmt(_delta_value(baseline[key], donchian[key]))} |"
        )
    lines.extend(
        [
            "",
            "## Primary deltas (Donchian vs Baseline)",
            "",
            f"- DELTA_NET_PNL: `{_fmt(primary['DELTA_NET_PNL'])}`",
            f"- DELTA_RETURN_PCT: `{_fmt(primary['DELTA_RETURN_PCT'])}`",
            f"- DELTA_MAX_DRAWDOWN: `{_fmt(primary['DELTA_MAX_DRAWDOWN'])}`",
            f"- DELTA_PROFIT_FACTOR: `{_fmt(primary['DELTA_PROFIT_FACTOR'])}`",
            f"- DELTA_EXPECTANCY: `{_fmt(primary['DELTA_EXPECTANCY'])}`",
            f"- DELTA_WIN_RATE: `{_fmt(primary['DELTA_WIN_RATE'])}`",
            f"- DELTA_TRADES: `{_fmt(primary['DELTA_TRADES'])}`",
            f"- DELTA_FEES: `{_fmt(primary['DELTA_FEES'])}`",
            f"- DELTA_SLIPPAGE: `{_fmt(primary['DELTA_SLIPPAGE'])}`",
            "",
            "## Signal / execution attribution (EthDonchianBreakout-v1)",
            "",
            f"- DONCHIAN_BUY_SIGNALS: `{attribution['DONCHIAN_BUY_SIGNALS']}`",
            f"- DONCHIAN_SELL_SIGNALS: `{attribution['DONCHIAN_SELL_SIGNALS']}`",
            f"- EXECUTED_BUYS: `{attribution['EXECUTED_BUYS']}`",
            f"- EXECUTED_SELLS: `{attribution['EXECUTED_SELLS']}`",
            f"- REJECTED_BUYS: `{attribution['REJECTED_BUYS']}`",
            f"- SELL_SIGNALS_WITHOUT_POSITION: `{attribution['SELL_SIGNALS_WITHOUT_POSITION']}`",
            f"- SUPERSEDED_BUYS (signal overridden by an exit on the same candle): "
            f"`{attribution['SUPERSEDED_BUYS']}`",
            "",
            "## ADX / breakout diagnostics (descriptive)",
            "",
            f"- RAW_BREAKOUT_EVENTS: `{diagnostics['RAW_BREAKOUT_EVENTS']}`",
            f"- BREAKOUTS_CONFIRMED_BY_ADX: `{diagnostics['BREAKOUTS_CONFIRMED_BY_ADX']}`",
            f"- BREAKOUTS_BLOCKED_BY_ADX: `{diagnostics['BREAKOUTS_BLOCKED_BY_ADX']}`",
            "",
            "Diagnostic only; ADX_MIN is not tuned from these results.",
            "",
            "## Trade structure",
            "",
            "| Metric | baseline-v1 | EthDonchianBreakout-v1 |",
            "|---|---|---|",
            f"| average_holding_duration_ms | "
            f"{_fmt(base_structure['average_holding_duration_ms'])} | "
            f"{_fmt(donchian_structure['average_holding_duration_ms'])} |",
            f"| median_holding_duration_ms | "
            f"{_fmt(base_structure['median_holding_duration_ms'])} | "
            f"{_fmt(donchian_structure['median_holding_duration_ms'])} |",
            f"| average_trade_pnl | {_fmt(base_structure['average_trade_pnl'])} | "
            f"{_fmt(donchian_structure['average_trade_pnl'])} |",
            f"| largest_win | {_fmt(base_structure['largest_win'])} | "
            f"{_fmt(donchian_structure['largest_win'])} |",
            f"| largest_loss | {_fmt(base_structure['largest_loss'])} | "
            f"{_fmt(donchian_structure['largest_loss'])} |",
            "",
            "## Predeclared interpretation",
            "",
            "IMPROVED iff expectancy, profit factor and net PnL improve while max drawdown "
            f"does not worsen by more than `{_fmt(MAX_DRAWDOWN_MATERIAL_ABS)}` absolute; "
            "NOT_IMPROVED when no metric improves or at least two of the three economic "
            "metrics deteriorate; otherwise MIXED. No composite score.",
            "",
            "## Safety",
            "",
            f"- WALK_FORWARD_READS: `{report['WALK_FORWARD_READS']}`",
            f"- FINAL_HOLDOUT_READS: `{report['FINAL_HOLDOUT_READS']}`",
            f"- FINAL_HOLDOUT_EXECUTIONS: `{report['FINAL_HOLDOUT_EXECUTIONS']}`",
            f"- HOLDOUT_STATE: `{report['HOLDOUT_STATE']}`",
            "",
            "Development may orient which candidate deserves to advance, but it does not "
            "demonstrate out-of-sample edge. EDGE_PRESENT and STRATEGY_PROMOTABLE remain "
            "NOT_EVALUATED.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate(
    *,
    repo_root: Path = REPO_ROOT,
    row_start: int = DEFAULT_ROW_START,
    row_end: int = DEFAULT_ROW_END,
    registry_root: Path,
    app_sha: str,
) -> dict[str, Any]:
    """Run the baseline vs Donchian comparison and return the evidence mapping."""
    if row_start < DEVELOPMENT_START or row_start >= row_end or row_end > DEVELOPMENT_END:
        raise ValueError("evaluation range must stay inside DEVELOPMENT")
    if is_holdout_range(row_start, row_end):
        raise ValueError("evaluation range intersects FINAL_HOLDOUT")

    requested_ranges: list[tuple[str, int, int]] = []

    def open_range(symbol: str) -> FrozenDatasetAdapter:
        requested_ranges.append((symbol, row_start, row_end))
        return FrozenDatasetAdapter.from_repo(
            repo_root,
            symbol=symbol,
            timeframe=TIMEFRAME,
            row_start=row_start,
            row_end=row_end,
        )

    primary = open_range(PRIMARY_SYMBOL)

    resolver = ImportlibSourceResolver()
    baseline_identity = strategy_artifact_identity(_baseline_definition(), resolver)
    donchian_identity = strategy_artifact_identity(donchian_definition(), resolver)
    if baseline_identity == donchian_identity:
        raise RuntimeError("strategy artifact identities must differ")
    kernel = make_kernel_identity(resolver, real_strategy_contract_source())

    baseline_spec = _build_spec(
        dataset=_dataset(row_start, row_end),
        name="ema-rsi-baseline",
        version="baseline-v1",
        artifact_identity=baseline_identity,
        kernel=kernel,
    )
    donchian_spec = _build_spec(
        dataset=_dataset(row_start, row_end),
        name=EthDonchianBreakout.strategy_name,
        version=EthDonchianBreakout.version,
        artifact_identity=donchian_identity,
        kernel=kernel,
    )

    registry = ExperimentRegistry(registry_root)
    baseline_spec_id = registry.register_spec(baseline_spec)
    donchian_spec_id = registry.register_spec(donchian_spec)

    baseline_probe = EmaRsiBaseline()
    baseline_signals = tuple(baseline_probe.on_candle(candle) for candle in primary.candles)
    donchian_probe = EthDonchianBreakout(candles=primary.candles)
    donchian_signals = tuple(donchian_probe.on_candle(candle) for candle in primary.candles)

    baseline_result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=baseline_spec_id,
    ).run()
    donchian_result = LabSessionRunner(
        adapter=primary,
        strategy=EthDonchianBreakout(candles=primary.candles),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=donchian_spec_id,
    ).run()
    donchian_result_repeat = LabSessionRunner(
        adapter=primary,
        strategy=EthDonchianBreakout(candles=primary.candles),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=donchian_spec_id,
    ).run()

    baseline_run = ExperimentRun(
        baseline_spec_id,
        "19b-baseline-run-1",
        RUN_1_CREATED_AT,
        app_sha,
        "ok",
        baseline_result.event_trace_hash,
        baseline_result.metrics_hash_value,
    )
    donchian_run = ExperimentRun(
        donchian_spec_id,
        "19b-donchian-run-1",
        RUN_1_CREATED_AT,
        app_sha,
        "ok",
        donchian_result.event_trace_hash,
        donchian_result.metrics_hash_value,
    )
    donchian_run_repeat = ExperimentRun(
        donchian_spec_id,
        "19b-donchian-run-2",
        RUN_2_CREATED_AT,
        app_sha,
        "ok",
        donchian_result_repeat.event_trace_hash,
        donchian_result_repeat.metrics_hash_value,
    )
    registry.register_run(baseline_run)
    registry.register_run(donchian_run)
    registry.register_run(donchian_run_repeat)

    reproducibility = compare_runs(donchian_run, donchian_run_repeat)

    baseline_metrics = {**count_signals(baseline_signals), **session_metrics(baseline_result)}
    donchian_metrics = {**count_signals(donchian_signals), **session_metrics(donchian_result)}
    raw_primary = compare_metrics(baseline_metrics, donchian_metrics)
    primary_deltas = {
        "DELTA_NET_PNL": raw_primary["delta_net_pnl"],
        "DELTA_RETURN_PCT": raw_primary["delta_return_pct"],
        "DELTA_MAX_DRAWDOWN": raw_primary["delta_max_drawdown"],
        "DELTA_PROFIT_FACTOR": raw_primary["delta_profit_factor"],
        "DELTA_EXPECTANCY": raw_primary["delta_expectancy"],
        "DELTA_WIN_RATE": _delta_value(baseline_metrics["win_rate"], donchian_metrics["win_rate"]),
        "DELTA_TRADES": raw_primary["delta_trades"],
        "DELTA_FEES": raw_primary["delta_fees"],
        "DELTA_SLIPPAGE": raw_primary["delta_slippage"],
    }

    attribution = execution_attribution(donchian_signals, donchian_result)
    diagnostics = breakout_diagnostics(primary.candles)
    if diagnostics["BREAKOUTS_CONFIRMED_BY_ADX"] != attribution["DONCHIAN_BUY_SIGNALS"]:
        raise RuntimeError("breakout diagnostics disagree with strategy BUY signals")

    development_result = classify_development_result(baseline_metrics, donchian_metrics)

    holdout_reads = sum(1 for _, start, end in requested_ranges if is_holdout_range(start, end))
    walk_forward_reads = sum(
        1
        for _, start, end in requested_ranges
        if start < WALK_FORWARD_END and end > WALK_FORWARD_START
    )
    holdout_state = json.loads(
        (repo_root / "holdout" / "v1.state.json").read_text(encoding="utf-8")
    )["state"]

    return {
        "PHASE": "19B",
        "EVALUATION": "DEVELOPMENT_ECONOMIC",
        "DATASET_ID": DATASET_ID,
        "PRIMARY_SYMBOL": PRIMARY_SYMBOL,
        "TIMEFRAME": TIMEFRAME,
        "ROW_START": row_start,
        "ROW_END": row_end,
        "REQUESTED_RANGES": [
            {"symbol": symbol, "row_start": start, "row_end": end}
            for symbol, start, end in requested_ranges
        ],
        "BASELINE_SPEC_ID": baseline_spec_id,
        "DONCHIAN_SPEC_ID": donchian_spec_id,
        "SPEC_IDS_DIFFERENT": baseline_spec_id != donchian_spec_id,
        "BASELINE": baseline_metrics,
        "DONCHIAN": donchian_metrics,
        "PRIMARY_DELTAS": primary_deltas,
        "SIGNAL_EXECUTION_ATTRIBUTION": attribution,
        "ADX_BREAKOUT_DIAGNOSTICS": diagnostics,
        "TRADE_STRUCTURE": {
            "baseline-v1": trade_structure(baseline_result),
            "EthDonchianBreakout-v1": trade_structure(donchian_result),
        },
        "DEVELOPMENT_RESULT": development_result,
        "WALK_FORWARD_CANDIDATE": "YES" if development_result == "IMPROVED" else "NO",
        "EDGE_PRESENT": "NOT_EVALUATED_OUT_OF_SAMPLE",
        "STRATEGY_PROMOTABLE": "NOT_EVALUATED",
        "REPRODUCIBILITY": "PASS" if reproducibility.reproducible else "FAIL",
        "REPRODUCIBILITY_DETAIL": {
            "same_spec_id": reproducibility.same_spec_id,
            "event_trace_hash_match": reproducibility.event_trace_hash_match,
            "metrics_hash_match": reproducibility.metrics_hash_match,
        },
        "WALK_FORWARD_READS": walk_forward_reads,
        "FINAL_HOLDOUT_READS": holdout_reads,
        "FINAL_HOLDOUT_EXECUTIONS": 0,
        "HOLDOUT_STATE": holdout_state,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phase19b-development-evaluation", description=__doc__)
    parser.add_argument("--row-start", type=int, default=DEFAULT_ROW_START)
    parser.add_argument("--row-end", type=int, default=DEFAULT_ROW_END)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--registry-dir", type=Path, default=None)
    parser.add_argument("--app-sha", default=None)
    args = parser.parse_args(argv)

    registry_dir = args.registry_dir or args.output_dir / "registry"
    report = evaluate(
        repo_root=REPO_ROOT,
        row_start=args.row_start,
        row_end=args.row_end,
        registry_root=registry_dir,
        app_sha=args.app_sha or _git_head(REPO_ROOT),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_jsonable(report), indent=2, sort_keys=True) + "\n"
    (args.output_dir / "development-comparison.json").write_text(payload, encoding="utf-8")
    (args.output_dir / "development-comparison.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
