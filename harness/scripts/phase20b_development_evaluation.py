#!/usr/bin/env python3
"""Phase 20B — DEVELOPMENT economic evaluation: baseline-v1 vs EthBollingerMeanReversion-v1.

Runs both strategies over DEVELOPMENT [0, 62208) with the real
FrozenDatasetAdapter + LabSessionRunner + PaperEngine + RiskEngine, persists both
experiments via ExperimentRegistry, computes the relative classification, the
Phase 19C absolute viability gate and walk-forward eligibility, and writes the
comparison evidence with mean-reversion diagnostics and a baseline behavior
anchor check.

Never touches WALK_FORWARD [62208, 88128) nor FINAL_HOLDOUT [88128, 103680).
Reuses the pure helpers from `lab.development_evaluation` (Phase 18B) and the
implemented Phase 19C gate (`lab.viability`); no historical artifact is modified.
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
from domain.market.indicators import adx, bollinger
from domain.risk.config import RiskConfig
from domain.trading.signal import Action
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
from lab.strategies.eth_bollinger_mean_reversion import (
    EthBollingerMeanReversion,
)
from lab.strategies.eth_bollinger_mean_reversion import (
    strategy_definition as bollinger_definition,
)
from lab.viability import AbsoluteViabilityEvidence, walk_forward_eligible
from lab.walk_forward import trades_from_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_SYMBOL = "ETHUSDT"
TIMEFRAME = "15m"
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
DEFAULT_ROW_START = DEVELOPMENT_START
DEFAULT_ROW_END = DEVELOPMENT_END
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "phases" / "20B" / "evidence"
RUN_1_CREATED_AT = "2026-09-13T05:00:00+00:00"
RUN_2_CREATED_AT = "2026-09-13T05:00:01+00:00"

BOLLINGER_PERIOD = 20
BOLLINGER_MULTIPLIER = 2.0
ADX_PERIOD = 14
ADX_MAX = 20.0

# Historical Phase 19B baseline anchor (must not drift).
BASELINE_ANCHOR_TRADES = 406
BASELINE_ANCHOR_NET_PNL = -20.023553665527754
BASELINE_ANCHOR_PROFIT_FACTOR = 0.3902907027103561
BASELINE_ANCHOR_EXPECTANCY = -0.049319097698344215
BASELINE_ANCHOR_MAX_DRAWDOWN = 0.01677501041581718
BASELINE_SPEC_ID_19B = "8979ff8479d9e17ccc17da52f81f1fe25d7c83b5a69419257f307a151929da67"

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


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


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
    donchian_signals: Sequence[Any], result: LabSessionResult
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
        "BUY_SIGNALS": buy_signals,
        "SELL_SIGNALS": sell_signals,
        "EXECUTED_BUYS": executed_buys,
        "EXECUTED_SELLS": executed_sells,
        "REJECTED_BUYS": rejected_buys,
        "SELL_SIGNALS_WITHOUT_POSITION": sell_without_position,
        "SUPERSEDED_BUYS": buy_signals - executed_buys - rejected_buys,
    }


def mean_reversion_diagnostics(candles: Sequence[Candle]) -> dict[str, int]:
    """Descriptive Bollinger/ADX accounting for the mean-reversion setup."""
    closes = [candle.close for candle in candles]
    bands = bollinger(closes, BOLLINGER_PERIOD, BOLLINGER_MULTIPLIER)
    adx_values = adx(candles, ADX_PERIOD)
    raw_excursions = 0
    reentry_events = 0
    confirmed = 0
    simultaneous = 0
    for index in range(1, len(candles)):
        previous = bands[index - 1]
        current = bands[index]
        if previous is None or current is None:
            continue
        if closes[index] < current.lower:
            raw_excursions += 1
        if closes[index - 1] < previous.lower and closes[index] >= current.lower:
            reentry_events += 1
            adx_value = adx_values[index]
            if adx_value is not None and adx_value < ADX_MAX:
                confirmed += 1
                if closes[index] >= current.middle:
                    simultaneous += 1
    return {
        "RAW_LOWER_BAND_EXCURSIONS": raw_excursions,
        "REENTRY_EVENTS": reentry_events,
        "REENTRIES_CONFIRMED_LOW_ADX": confirmed,
        "REENTRIES_BLOCKED_BY_ADX": reentry_events - confirmed,
        "SIMULTANEOUS_BUY_SELL_SETUPS": simultaneous,
        "SELL_PRECEDENCE_EVENTS": simultaneous,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the comparison, viability, eligibility and diagnostics."""
    baseline = report["BASELINE"]
    bollinger_metrics = report["BOLLINGER"]
    primary = report["PRIMARY_DELTAS"]
    diagnostics = report["MEAN_REVERSION_DIAGNOSTICS"]
    attribution = report["SIGNAL_EXECUTION_ATTRIBUTION"]
    viability = report["ABSOLUTE_VIABILITY"]
    lines = [
        "# Phase 20B — DEVELOPMENT Economic Evaluation (baseline vs Bollinger)",
        "",
        f"- A baseline-v1: `{report['BASELINE_SPEC_ID']}`",
        f"- B EthBollingerMeanReversion-v1: `{report['BOLLINGER_SPEC_ID']}`",
        f"- Slice: DEVELOPMENT `[{report['ROW_START']}, {report['ROW_END']})`",
        f"- SpecIds differ: `{report['SPEC_IDS_DIFFERENT']}`",
        f"- Baseline identity changed: `{report['BASELINE_IDENTITY_CHANGED']}`",
        f"- Baseline behavior changed: `{report['BASELINE_BEHAVIOR_CHANGED']}`",
        f"- Reproducibility: `{report['REPRODUCIBILITY']}`",
        f"- Development result: `{report['DEVELOPMENT_RESULT']}`",
        f"- Absolute viability gate: `{viability['ABSOLUTE_VIABILITY_GATE']}`",
        f"- Walk-forward eligible: `{report['WALK_FORWARD_ELIGIBLE']}` "
        f"(authorized: `{report['WALK_FORWARD_AUTHORIZED']}`)",
        f"- Edge present: `{report['EDGE_PRESENT']}`",
        f"- Strategy promotable: `{report['STRATEGY_PROMOTABLE']}`",
        "",
        "| Metric | baseline-v1 | EthBollingerMeanReversion-v1 | Delta |",
        "|---|---|---|---|",
    ]
    for key, label in METRIC_ROWS:
        lines.append(
            f"| {label} | {_fmt(baseline[key])} | {_fmt(bollinger_metrics[key])} | "
            f"{_fmt(_delta_value(baseline[key], bollinger_metrics[key]))} |"
        )
    lines.extend(
        [
            "",
            "## Primary deltas (Bollinger vs Baseline)",
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
            "## Absolute viability (Phase 19C)",
            "",
            f"- NET_PNL_GT_0: `{viability['NET_PNL_GT_0']}`",
            f"- EXPECTANCY_GT_0: `{viability['EXPECTANCY_GT_0']}`",
            f"- PROFIT_FACTOR_GT_1: `{viability['PROFIT_FACTOR_GT_1']}`",
            f"- ABSOLUTE_VIABILITY_GATE: `{viability['ABSOLUTE_VIABILITY_GATE']}`",
            "",
            "## Mean-reversion diagnostics (descriptive)",
            "",
            f"- RAW_LOWER_BAND_EXCURSIONS: `{diagnostics['RAW_LOWER_BAND_EXCURSIONS']}`",
            f"- REENTRY_EVENTS: `{diagnostics['REENTRY_EVENTS']}`",
            f"- REENTRIES_CONFIRMED_LOW_ADX: `{diagnostics['REENTRIES_CONFIRMED_LOW_ADX']}`",
            f"- REENTRIES_BLOCKED_BY_ADX: `{diagnostics['REENTRIES_BLOCKED_BY_ADX']}`",
            f"- SIMULTANEOUS_BUY_SELL_SETUPS: `{diagnostics['SIMULTANEOUS_BUY_SELL_SETUPS']}`",
            f"- SELL_PRECEDENCE_EVENTS: `{diagnostics['SELL_PRECEDENCE_EVENTS']}`",
            "",
            "Identity: `REENTRY_EVENTS = REENTRIES_CONFIRMED_LOW_ADX + "
            "REENTRIES_BLOCKED_BY_ADX`; `SELL_PRECEDENCE_EVENTS <= "
            "SIMULTANEOUS_BUY_SELL_SETUPS`. BUY_SIGNALS = confirmed re-entries minus "
            "simultaneous setups (SELL precedence).",
            "",
            "## Signal / execution attribution",
            "",
            f"- BUY_SIGNALS: `{attribution['BUY_SIGNALS']}`",
            f"- SELL_SIGNALS: `{attribution['SELL_SIGNALS']}`",
            f"- EXECUTED_BUYS: `{attribution['EXECUTED_BUYS']}`",
            f"- EXECUTED_SELLS: `{attribution['EXECUTED_SELLS']}`",
            f"- REJECTED_BUYS: `{attribution['REJECTED_BUYS']}`",
            f"- SELL_SIGNALS_WITHOUT_POSITION: `{attribution['SELL_SIGNALS_WITHOUT_POSITION']}`",
            "",
            "## Baseline behavior anchor",
            "",
            "| Metric | expected (19B) | actual | match |",
            "|---|---|---|---|",
        ]
    )
    anchor = report["BASELINE_ANCHOR"]
    for label, expected_key, actual_key in (
        ("closed_trades", "expected_trades", "actual_trades"),
        ("net_pnl", "expected_net_pnl", "actual_net_pnl"),
        ("profit_factor", "expected_profit_factor", "actual_profit_factor"),
        ("expectancy", "expected_expectancy", "actual_expectancy"),
        ("max_drawdown", "expected_max_drawdown", "actual_max_drawdown"),
    ):
        lines.append(
            f"| {label} | {_fmt(anchor[expected_key])} | {_fmt(anchor[actual_key])} | "
            f"{anchor['match']} |"
        )
    lines.extend(
        [
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
    """Run the baseline vs Bollinger comparison and return the evidence mapping."""
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
    bollinger_identity = strategy_artifact_identity(bollinger_definition(), resolver)
    if baseline_identity == bollinger_identity:
        raise RuntimeError("strategy artifact identities must differ")
    kernel = make_kernel_identity(resolver, real_strategy_contract_source())

    baseline_spec = _build_spec(
        dataset=_dataset(row_start, row_end),
        name="ema-rsi-baseline",
        version="baseline-v1",
        artifact_identity=baseline_identity,
        kernel=kernel,
    )
    bollinger_spec = _build_spec(
        dataset=_dataset(row_start, row_end),
        name=EthBollingerMeanReversion.strategy_name,
        version=EthBollingerMeanReversion.version,
        artifact_identity=bollinger_identity,
        kernel=kernel,
    )

    registry = ExperimentRegistry(registry_root)
    baseline_spec_id = registry.register_spec(baseline_spec)
    bollinger_spec_id = registry.register_spec(bollinger_spec)

    baseline_probe = EmaRsiBaseline()
    baseline_signals = tuple(baseline_probe.on_candle(candle) for candle in primary.candles)
    bollinger_probe = EthBollingerMeanReversion(candles=primary.candles)
    bollinger_signals = tuple(bollinger_probe.on_candle(candle) for candle in primary.candles)

    baseline_result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=baseline_spec_id,
    ).run()
    bollinger_result = LabSessionRunner(
        adapter=primary,
        strategy=EthBollingerMeanReversion(candles=primary.candles),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=bollinger_spec_id,
    ).run()
    bollinger_result_repeat = LabSessionRunner(
        adapter=primary,
        strategy=EthBollingerMeanReversion(candles=primary.candles),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=bollinger_spec_id,
    ).run()

    baseline_run = ExperimentRun(
        baseline_spec_id,
        "20b-baseline-run-1",
        RUN_1_CREATED_AT,
        app_sha,
        "ok",
        baseline_result.event_trace_hash,
        baseline_result.metrics_hash_value,
    )
    bollinger_run = ExperimentRun(
        bollinger_spec_id,
        "20b-bollinger-run-1",
        RUN_1_CREATED_AT,
        app_sha,
        "ok",
        bollinger_result.event_trace_hash,
        bollinger_result.metrics_hash_value,
    )
    bollinger_run_repeat = ExperimentRun(
        bollinger_spec_id,
        "20b-bollinger-run-2",
        RUN_2_CREATED_AT,
        app_sha,
        "ok",
        bollinger_result_repeat.event_trace_hash,
        bollinger_result_repeat.metrics_hash_value,
    )
    registry.register_run(baseline_run)
    registry.register_run(bollinger_run)
    registry.register_run(bollinger_run_repeat)

    reproducibility = compare_runs(bollinger_run, bollinger_run_repeat)

    baseline_metrics = {**count_signals(baseline_signals), **session_metrics(baseline_result)}
    bollinger_metrics = {**count_signals(bollinger_signals), **session_metrics(bollinger_result)}
    raw_primary = compare_metrics(baseline_metrics, bollinger_metrics)
    primary_deltas = {
        "DELTA_NET_PNL": raw_primary["delta_net_pnl"],
        "DELTA_RETURN_PCT": raw_primary["delta_return_pct"],
        "DELTA_MAX_DRAWDOWN": raw_primary["delta_max_drawdown"],
        "DELTA_PROFIT_FACTOR": raw_primary["delta_profit_factor"],
        "DELTA_EXPECTANCY": raw_primary["delta_expectancy"],
        "DELTA_WIN_RATE": _delta_value(baseline_metrics["win_rate"], bollinger_metrics["win_rate"]),
        "DELTA_TRADES": raw_primary["delta_trades"],
        "DELTA_FEES": raw_primary["delta_fees"],
        "DELTA_SLIPPAGE": raw_primary["delta_slippage"],
    }

    development_result = classify_development_result(baseline_metrics, bollinger_metrics)

    viability = AbsoluteViabilityEvidence(
        net_pnl=float(bollinger_metrics["net_pnl"]),
        expectancy=bollinger_metrics["expectancy"],
        profit_factor=bollinger_metrics["profit_factor"],
    )
    gate_passed = viability.passed
    eligible = walk_forward_eligible(development_result, viability)

    diagnostics = mean_reversion_diagnostics(primary.candles)
    attribution = execution_attribution(bollinger_signals, bollinger_result)
    if diagnostics["REENTRY_EVENTS"] != (
        diagnostics["REENTRIES_CONFIRMED_LOW_ADX"] + diagnostics["REENTRIES_BLOCKED_BY_ADX"]
    ):
        raise RuntimeError("reentry diagnostic identity failed")
    expected_buys = (
        diagnostics["REENTRIES_CONFIRMED_LOW_ADX"] - diagnostics["SIMULTANEOUS_BUY_SELL_SETUPS"]
    )
    if expected_buys != attribution["BUY_SIGNALS"]:
        raise RuntimeError("breakout diagnostics disagree with strategy BUY signals")
    if diagnostics["SELL_PRECEDENCE_EVENTS"] > diagnostics["SIMULTANEOUS_BUY_SELL_SETUPS"]:
        raise RuntimeError("sell precedence exceeds simultaneous setups")

    full_range = row_start == DEVELOPMENT_START and row_end == DEVELOPMENT_END
    if full_range:
        anchor_match: bool | None = (
            baseline_metrics["closed_trades"] == BASELINE_ANCHOR_TRADES
            and _close(baseline_metrics["net_pnl"], BASELINE_ANCHOR_NET_PNL)
            and _close(baseline_metrics["profit_factor"], BASELINE_ANCHOR_PROFIT_FACTOR)
            and _close(baseline_metrics["expectancy"], BASELINE_ANCHOR_EXPECTANCY)
            and _close(baseline_metrics["max_drawdown"], BASELINE_ANCHOR_MAX_DRAWDOWN)
        )
        if not anchor_match:
            raise RuntimeError("BASELINE_BEHAVIOR_DRIFT_FOUND")
    else:
        anchor_match = None
    baseline_identity_changed = baseline_spec_id != BASELINE_SPEC_ID_19B

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
        "PHASE": "20B",
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
        "BOLLINGER_SPEC_ID": bollinger_spec_id,
        "SPEC_IDS_DIFFERENT": baseline_spec_id != bollinger_spec_id,
        "BASELINE_IDENTITY_CHANGED": baseline_identity_changed,
        "BASELINE_BEHAVIOR_CHANGED": anchor_match is False,
        "BASELINE_ANCHOR": {
            "expected_trades": BASELINE_ANCHOR_TRADES,
            "actual_trades": baseline_metrics["closed_trades"],
            "expected_net_pnl": BASELINE_ANCHOR_NET_PNL,
            "actual_net_pnl": baseline_metrics["net_pnl"],
            "expected_profit_factor": BASELINE_ANCHOR_PROFIT_FACTOR,
            "actual_profit_factor": baseline_metrics["profit_factor"],
            "expected_expectancy": BASELINE_ANCHOR_EXPECTANCY,
            "actual_expectancy": baseline_metrics["expectancy"],
            "expected_max_drawdown": BASELINE_ANCHOR_MAX_DRAWDOWN,
            "actual_max_drawdown": baseline_metrics["max_drawdown"],
            "match": "NOT_APPLICABLE" if anchor_match is None else anchor_match,
        },
        "BASELINE": baseline_metrics,
        "BOLLINGER": bollinger_metrics,
        "PRIMARY_DELTAS": primary_deltas,
        "DEVELOPMENT_RESULT": development_result,
        "ABSOLUTE_VIABILITY": {
            "NET_PNL_GT_0": math.isfinite(float(bollinger_metrics["net_pnl"]))
            and float(bollinger_metrics["net_pnl"]) > 0.0,
            "EXPECTANCY_GT_0": bollinger_metrics["expectancy"] is not None
            and math.isfinite(float(bollinger_metrics["expectancy"]))
            and float(bollinger_metrics["expectancy"]) > 0.0,
            "PROFIT_FACTOR_GT_1": bollinger_metrics["profit_factor"] is not None
            and math.isfinite(float(bollinger_metrics["profit_factor"]))
            and float(bollinger_metrics["profit_factor"]) > 1.0,
            "ABSOLUTE_VIABILITY_GATE": "PASS" if gate_passed else "FAIL",
        },
        "WALK_FORWARD_ELIGIBLE": "YES" if eligible else "NO",
        "WALK_FORWARD_AUTHORIZED": "NO",
        "EDGE_PRESENT": "NOT_EVALUATED_OUT_OF_SAMPLE",
        "STRATEGY_PROMOTABLE": "NOT_EVALUATED",
        "MEAN_REVERSION_DIAGNOSTICS": diagnostics,
        "SIGNAL_EXECUTION_ATTRIBUTION": attribution,
        "TRADE_STRUCTURE": {
            "baseline-v1": trade_structure(baseline_result),
            "EthBollingerMeanReversion-v1": trade_structure(bollinger_result),
        },
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
    parser = argparse.ArgumentParser(prog="phase20b-development-evaluation", description=__doc__)
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
