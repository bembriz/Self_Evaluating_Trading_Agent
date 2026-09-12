#!/usr/bin/env python3
"""Phase 18B — DEVELOPMENT economic evaluation (baseline vs EmaRsiBtcContext).

Runs both strategies over the DEVELOPMENT slice [0, 62208) with the real
FrozenDatasetAdapter + LabSessionRunner + PaperEngine + RiskEngine, persists both
experiments via ExperimentRegistry and writes the comparison evidence.

Never touches WALK_FORWARD [62208, 88128) nor FINAL_HOLDOUT [88128, 103680); the
only WALK_FORWARD reuse is the pure metric helper `trades_from_trace`.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from lab.development_evaluation import (
    MAX_DRAWDOWN_MATERIAL_ABS,
    btc_filter_attribution,
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
from lab.session_runner import LabSessionRunner
from lab.splits import (
    DATASET_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    WALK_FORWARD_END,
    WALK_FORWARD_START,
    is_holdout_range,
)
from lab.strategies.ema_rsi_btc_context import EmaRsiBtcContext, strategy_definition

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_SYMBOL = "ETHUSDT"
CONTEXT_SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
STRATEGY_A = "baseline-v1"
STRATEGY_B = "EmaRsiBtcContext-v1"
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
DEFAULT_ROW_START = DEVELOPMENT_START
DEFAULT_ROW_END = DEVELOPMENT_END
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "phases" / "18B" / "evidence"
RUN_1_CREATED_AT = "2026-09-12T20:00:00+00:00"
RUN_2_CREATED_AT = "2026-09-12T20:00:01+00:00"

METRIC_ROWS: tuple[tuple[str, str], ...] = (
    ("signals_buy", "signals_buy"),
    ("signals_sell", "signals_sell"),
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
        strategy_version=STRATEGY_A,
        kind="deterministic",
        normalized_config={"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_exit": 80.0},
        sources=("domain.trading.strategy",),
    )


def _dataset(row_start: int, row_end: int, *, with_context: bool) -> dict[str, Any]:
    dataset: dict[str, Any] = {
        "dataset_id": DATASET_ID,
        "symbol": PRIMARY_SYMBOL,
        "timeframe": TIMEFRAME,
        "row_start": row_start,
        "row_end": row_end,
    }
    if with_context:
        dataset["context"] = {
            "symbol": CONTEXT_SYMBOL,
            "timeframe": TIMEFRAME,
            "row_start": row_start,
            "row_end": row_end,
        }
    return dataset


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


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the DEVELOPMENT comparison table + BTC filter attribution."""
    baseline = report["BASELINE"]
    candidate = report["BTC_CONTEXT"]
    attribution = report["BTC_FILTER_ATTRIBUTION"]
    lines = [
        "# Phase 18B — DEVELOPMENT Economic Evaluation",
        "",
        f"- Strategy A: `{report['STRATEGY_A']}` (spec `{report['BASELINE_SPEC_ID']}`)",
        f"- Strategy B: `{report['STRATEGY_B']}` (spec `{report['BTC_CONTEXT_SPEC_ID']}`)",
        f"- Slice: DEVELOPMENT `[{report['ROW_START']}, {report['ROW_END']})` "
        f"({report['PRIMARY_SYMBOL']} {report['TIMEFRAME']}, "
        f"{report['CONTEXT_SYMBOL']} {report['TIMEFRAME']} context only for B)",
        f"- SpecIds differ: `{report['SPEC_IDS_DIFFERENT']}`",
        f"- Reproducibility: `{report['REPRODUCIBILITY']}`",
        f"- Development result: `{report['DEVELOPMENT_RESULT']}`",
        f"- Walk-forward candidate: `{report['WALK_FORWARD_CANDIDATE']}`",
        f"- Edge present: `{report['EDGE_PRESENT']}`",
        f"- Strategy promotable: `{report['STRATEGY_PROMOTABLE']}`",
        "",
        "| Metric | baseline-v1 | EmaRsiBtcContext-v1 | delta |",
        "|---|---|---|---|",
    ]
    for key, label in METRIC_ROWS:
        base_value = baseline[key]
        cand_value = candidate[key]
        lines.append(
            f"| {label} | {_fmt(base_value)} | {_fmt(cand_value)} | "
            f"{_fmt(_delta_value(base_value, cand_value))} |"
        )
    lines.extend(
        [
            "",
            "## BTC filter attribution",
            "",
            f"- baseline_buy_candidates: `{attribution['baseline_buy_candidates']}`",
            f"- btc_confirmed_buys: `{attribution['btc_confirmed_buys']}`",
            f"- btc_blocked_buys: `{attribution['btc_blocked_buys']}`",
            f"- blocked baseline trades: `{attribution['blocked_baseline_trades']}`",
            f"- blocked baseline winners: `{attribution['blocked_baseline_winners']}`",
            f"- blocked baseline losers: `{attribution['blocked_baseline_losers']}`",
            f"- blocked baseline flats: `{attribution['blocked_baseline_flats']}`",
            f"- blocked baseline net PnL: `{_fmt(attribution['blocked_baseline_net_pnl'])}`",
            f"- blocked baseline avg net PnL: "
            f"`{_fmt(attribution['blocked_baseline_avg_net_pnl'])}`",
            f"- trade reduction: `{_fmt(report['COMPARISON']['trade_reduction_percent'])}%`",
            "",
            "## Predeclared interpretation",
            "",
            "IMPROVED requires expectancy, profit factor and net PnL to improve while "
            "max drawdown does not worsen by more than "
            f"`{_fmt(MAX_DRAWDOWN_MATERIAL_ABS)}` absolute; NOT_IMPROVED when no metric "
            "improves or at least two of the three economic metrics deteriorate; otherwise "
            "MIXED. No composite score.",
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
    """Run the full DEVELOPMENT comparison and return the evidence mapping."""
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
    context = open_range(CONTEXT_SYMBOL)

    resolver = ImportlibSourceResolver()
    baseline_identity = strategy_artifact_identity(_baseline_definition(), resolver)
    candidate_identity = strategy_artifact_identity(strategy_definition(), resolver)
    if baseline_identity == candidate_identity:
        raise RuntimeError("strategy artifact identities must differ")
    kernel = make_kernel_identity(resolver, real_strategy_contract_source())

    baseline_spec = _build_spec(
        dataset=_dataset(row_start, row_end, with_context=False),
        name="ema-rsi-baseline",
        version=STRATEGY_A,
        artifact_identity=baseline_identity,
        kernel=kernel,
    )
    candidate_spec = _build_spec(
        dataset=_dataset(row_start, row_end, with_context=True),
        name=EmaRsiBtcContext.strategy_name,
        version=EmaRsiBtcContext.version,
        artifact_identity=candidate_identity,
        kernel=kernel,
    )

    registry = ExperimentRegistry(registry_root)
    baseline_spec_id = registry.register_spec(baseline_spec)
    candidate_spec_id = registry.register_spec(candidate_spec)

    baseline_probe = EmaRsiBaseline()
    baseline_signals = tuple(baseline_probe.on_candle(candle) for candle in primary.candles)
    candidate_probe = EmaRsiBtcContext.from_adapters(primary=primary, context=context)
    candidate_signals = tuple(candidate_probe.on_candle(candle) for candle in primary.candles)

    baseline_result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=baseline_spec_id,
    ).run()
    candidate_result = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBtcContext.from_adapters(primary=primary, context=context),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=candidate_spec_id,
    ).run()
    candidate_result_repeat = LabSessionRunner(
        adapter=primary,
        strategy=EmaRsiBtcContext.from_adapters(primary=primary, context=context),
        engine=PaperEngine(config=ENGINE_CONFIG),
        experiment_spec_id=candidate_spec_id,
    ).run()

    baseline_run = ExperimentRun(
        baseline_spec_id,
        "18b-baseline-run-1",
        RUN_1_CREATED_AT,
        app_sha,
        "ok",
        baseline_result.event_trace_hash,
        baseline_result.metrics_hash_value,
    )
    candidate_run = ExperimentRun(
        candidate_spec_id,
        "18b-candidate-run-1",
        RUN_1_CREATED_AT,
        app_sha,
        "ok",
        candidate_result.event_trace_hash,
        candidate_result.metrics_hash_value,
    )
    candidate_run_repeat = ExperimentRun(
        candidate_spec_id,
        "18b-candidate-run-2",
        RUN_2_CREATED_AT,
        app_sha,
        "ok",
        candidate_result_repeat.event_trace_hash,
        candidate_result_repeat.metrics_hash_value,
    )
    registry.register_run(baseline_run)
    registry.register_run(candidate_run)
    registry.register_run(candidate_run_repeat)

    reproducibility = compare_runs(candidate_run, candidate_run_repeat)

    baseline_metrics = {**count_signals(baseline_signals), **session_metrics(baseline_result)}
    candidate_metrics = {**count_signals(candidate_signals), **session_metrics(candidate_result)}
    comparison = compare_metrics(baseline_metrics, candidate_metrics)
    attribution = btc_filter_attribution(baseline_signals, candidate_signals, baseline_result)
    development_result = classify_development_result(baseline_metrics, candidate_metrics)

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
        "PHASE": "18B",
        "EVALUATION": "DEVELOPMENT_ECONOMIC",
        "STRATEGY_A": STRATEGY_A,
        "STRATEGY_B": STRATEGY_B,
        "DATASET_ID": DATASET_ID,
        "PRIMARY_SYMBOL": PRIMARY_SYMBOL,
        "CONTEXT_SYMBOL": CONTEXT_SYMBOL,
        "TIMEFRAME": TIMEFRAME,
        "ROW_START": row_start,
        "ROW_END": row_end,
        "REQUESTED_RANGES": [
            {"symbol": symbol, "row_start": start, "row_end": end}
            for symbol, start, end in requested_ranges
        ],
        "BASELINE_SPEC_ID": baseline_spec_id,
        "BTC_CONTEXT_SPEC_ID": candidate_spec_id,
        "SPEC_IDS_DIFFERENT": baseline_spec_id != candidate_spec_id,
        "BASELINE": baseline_metrics,
        "BTC_CONTEXT": candidate_metrics,
        "COMPARISON": comparison,
        "BTC_FILTER_ATTRIBUTION": attribution,
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
    parser = argparse.ArgumentParser(prog="phase18b-development-evaluation", description=__doc__)
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
