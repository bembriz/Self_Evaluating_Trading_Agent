"""CLI Trade-Level Replay — stdlib puro.

Uso en lenovosrv (sin venv):

    python3 -m infrastructure.medallion.replay_cli \\
        --dataset-dir /srv/data/medallion/gold/replay-datasets/ETHUSDT/<dataset_id> \\
        --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \\
        --candles-dir /srv/data/medallion/silver/candles/ETHUSDT \\
        --ledger-path /srv/fast/medallion/replay-work/ledger.jsonl \\
        --require-marker /srv/data/.lenovosrv-data-volume

Exit codes: 0 OK · 1 replay/dataset/IO · 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from domain.market.candle import Candle
from domain.trading.strategy import Strategy
from infrastructure.medallion.bronze import BronzeError, ensure_marker
from infrastructure.medallion.replay import (
    DEFAULT_SCENARIO,
    CandleRow,
    DecisionProvider,
    ReplayScenario,
    ReplayTrade,
    ScriptedScheduleProvider,
    iter_trades,
    ledger_payload,
    load_candles,
    replay_engine,
    validate_dataset,
    write_ledger,
)
from infrastructure.medallion.split_guard import SplitGuardError
from infrastructure.medallion.strategy_provider import (
    StrategyDecisionProvider,
    rows_to_domain_candles,
)

EXIT_OK = 0
EXIT_REPLAY_ERROR = 1
EXIT_USAGE = 2

STRATEGY_CHOICES = ("scripted", "ema-rsi", "donchian", "bollinger")
SIZING_CHOICES = ("fixed", "risk_engine")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trade-level replay (dos relojes, idempotente)")
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--trades-dir", required=True, type=Path)
    parser.add_argument("--candles-dir", required=True, type=Path)
    parser.add_argument("--ledger-path", required=True, type=Path)
    parser.add_argument("--require-marker", type=Path, default=None)
    parser.add_argument(
        "--strategy",
        choices=STRATEGY_CHOICES,
        default="scripted",
        help="estrategia: scripted (legacy M7) o congeladas M9-B",
    )
    parser.add_argument(
        "--sizing-mode",
        choices=SIZING_CHOICES,
        default=None,
        help="fixed (legacy) o risk_engine (M9-B); por defecto: fixed para "
        "scripted, risk_engine para las estrategias congeladas",
    )
    return parser


def _m9b_scenario(strategy_version: str, sizing_mode: str) -> ReplayScenario:
    """Escenario M9-B = reglas Phase 22B explícitas (nunca defaults M7)."""
    scenario_id = "m9b-22b-parity-v1" if sizing_mode == "risk_engine" else "m9b-strategy-fixed-v1"
    from domain.risk.config import RiskConfig

    return ReplayScenario(
        scenario_id=scenario_id,
        risk=RiskConfig(stop_loss_required=True, version="risk-v2-atr-exit"),
        quantity=0.01,
        fee_rate=0.001,  # 10 bps (Phase 22B)
        slippage_bps=2.0,  # 2 bps (Phase 22B)
        strategy_version=strategy_version,
        atr_period=14,
        sizing_mode=sizing_mode,
        intensity="medium",
    )


def _build_strategy(name: str, domain_candles: tuple[Candle, ...]) -> Strategy:
    # Composition root: la construcción de estrategias congeladas vive aquí
    # (import diferido para no acoplar el módulo a lab en el modo scripted).
    if name == "ema-rsi":
        from domain.trading.strategy import EmaRsiBaseline

        return EmaRsiBaseline()
    if name == "donchian":
        from lab.strategies.eth_donchian_breakout import EthDonchianBreakout

        return EthDonchianBreakout(candles=domain_candles)
    if name == "bollinger":
        from lab.strategies.eth_bollinger_mean_reversion import EthBollingerMeanReversion

        return EthBollingerMeanReversion(candles=domain_candles)
    raise ValueError(f"estrategia desconocida {name!r}")


def _resolve_scenario_and_provider(
    args: argparse.Namespace, candles_15m: list[CandleRow]
) -> tuple[ReplayScenario, DecisionProvider]:
    sizing = args.sizing_mode
    if args.strategy == "scripted":
        resolved = sizing or "fixed"
        provider: DecisionProvider = ScriptedScheduleProvider()
        if resolved == "fixed":
            # Ruta legacy exacta: mismo objeto de escenario que el UAT M7.
            return DEFAULT_SCENARIO, provider
        return _m9b_scenario("scripted-schedule-v1", resolved), provider
    resolved = sizing or "risk_engine"
    domain_candles = rows_to_domain_candles(candles_15m)
    strategy = _build_strategy(args.strategy, domain_candles)
    return (
        _m9b_scenario(strategy.version, resolved),
        StrategyDecisionProvider(strategy=strategy, candle_rows=candles_15m),
    )


def _counting_trades(
    trades: Iterable[ReplayTrade], counter: dict[str, int]
) -> Iterator[ReplayTrade]:
    for trade in trades:
        counter["trades"] += 1
        yield trade


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    counter = {"trades": 0}
    try:
        if args.require_marker is not None:
            ensure_marker(args.require_marker)
        dataset = validate_dataset(args.dataset_dir, args.trades_dir, args.candles_dir)
        candles = load_candles(dataset, ("15m", "1h", "4h"))
        scenario, provider = _resolve_scenario_and_provider(args, candles["15m"])
        result = replay_engine(
            candles["15m"],
            candles["1h"],
            candles["4h"],
            _counting_trades(iter_trades(dataset), counter),
            scenario,
            provider,
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
        )
        payload = ledger_payload(
            result,
            dataset_id=dataset.dataset_id,
            dataset_sha=dataset.dataset_sha,
            symbol=dataset.symbol,
            dates=dataset.dates,
            ordering_fidelity=dataset.ordering_fidelity,
            scenario=scenario,
        )
        status = write_ledger(args.ledger_path, payload)
    except (BronzeError, SplitGuardError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_REPLAY_ERROR

    created = 1 if status == "created" else 0
    skipped = 1 if status == "skipped" else 0
    ledger_sha = hashlib.sha256(payload).hexdigest()
    print(
        f"STATUS={status} dataset_id={dataset.dataset_id} "
        f"dataset_sha256={dataset.dataset_sha} ledger_sha256={ledger_sha}"
    )
    stats = result.stats
    print(
        f"SUMMARY created={created} skipped={skipped} "
        f"decisions_total={stats['decisions_total']} "
        f"decisions_filled={stats['decisions_filled']} "
        f"decisions_dropped={stats['decisions_dropped']} "
        f"decisions_unfilled={stats['decisions_unfilled']} "
        f"closed_trades={stats['closed_trades']} trades={counter['trades']}"
    )
    if scenario.sizing_mode != "fixed":
        # Solo modo dinámico: stdout legacy (scripted fixed) permanece
        # byte-idéntico a los greps m7 (STATUS/SUMMARY).
        print(
            f"SIZING=dynamic mode={scenario.sizing_mode} "
            f"intensity={scenario.intensity} "
            f"decisions_rejected={stats.get('decisions_rejected', 0)} "
            f"rejected_reasons={json.dumps(dict(sorted(result.rejected_reasons.items())))}"
        )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
