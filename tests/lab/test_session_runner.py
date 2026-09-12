"""Tests fase 17D: LabSessionRunner — parity, determinismo e integración.

Paridad no tautológica: la misma secuencia controlada se ejecuta por dos
caminos independientes (LabSessionRunner vs PaperRunner.handle_kline real, con
instancias frescas de estrategia y motor) y se comparan decisiones, órdenes,
fills, equity, PnL, fees, slippage y rechazos de riesgo. El caso precomputado
además se ancora a valores calculados a mano.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.paper_engine import PaperEngine
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from domain.market.candle import Candle, Timeframe
from domain.market.stream import KlineUpdate
from domain.risk.config import RiskConfig
from domain.trading.signal import Action
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig, PrecomputedStrategy
from lab.experiment_spec import ExperimentRun, ExperimentSpec, spec_id
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.session_runner import LabSessionRunner, summarize_lab_events

REPO = Path(__file__).resolve().parents[2]
SPEC_ID = "ab" * 32
RISK = RiskConfig(stop_loss_required=False)


def _candle(ts: int, close: float, ref: float) -> Candle:
    return Candle(
        timestamp_ms=ts,
        open=ref,
        high=max(ref, close) + 0.5,
        low=min(ref, close) - 0.5,
        close=close,
        volume=10.0,
        turnover=close * 10.0,
    )


def _write_tmp_dataset(tmp_path: Path, candles: list[Candle]) -> FrozenDatasetAdapter:
    csv_path = tmp_path / "ETHUSDT_15m.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_ms", "open", "high", "low", "close", "volume", "turnover"])
        for candle in candles:
            writer.writerow(
                [
                    candle.timestamp_ms,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    candle.turnover,
                ]
            )
    manifest = {
        "dataset_version": "BYBIT_ETHBTC_V001",
        "files": [
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "row_count": len(candles),
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "start_ms": candles[0].timestamp_ms,
                "end_ms": candles[-1].timestamp_ms,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return FrozenDatasetAdapter(
        dataset_id="BYBIT_ETHBTC_V001",
        symbol="ETHUSDT",
        timeframe="15m",
        manifest_path=manifest_path,
        csv_path=csv_path,
        expected_manifest_sha=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        row_start=0,
        row_end=len(candles),
    )


class _FakePaperRepo:
    def __init__(self) -> None:
        self.events: list[PaperTradeEvent] = []

    async def add(self, event: PaperTradeEvent) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        return [event for event in self.events if event.session_id == session_id]


def _paper_config() -> PaperRunnerConfig:
    return PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="parity-test",
    )


def _paper_trace(events: list[PaperTradeEvent]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp_ms": event.timestamp_ms,
            "action": event.action,
            "filled": event.filled,
            "exit_reason": event.exit_reason,
            "risk_reason": event.risk_reason,
            "exec_price": event.exec_price,
            "quantity": event.quantity,
            "fee": event.fee,
            "slippage_cost": event.slippage_cost,
            "equity": event.equity,
        }
        for event in events
    ]


async def _run_paper_path(candles: list[Candle], strategy: Any) -> list[PaperTradeEvent]:
    repo = _FakePaperRepo()
    runner = PaperRunner(
        config=_paper_config(),
        event_repo=repo,
        paper_engine=PaperEngine(config=RISK),
        strategy=strategy,
    )
    for candle in candles:
        kline = KlineUpdate(
            "ETHUSDT",
            Timeframe.M15,
            candle.timestamp_ms,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
            candle.turnover,
            True,
        )
        await runner.handle_kline(kline)
    return repo.events


def _controlled_candles() -> list[Candle]:
    t0 = 1_700_000_000_000
    return [
        _candle(t0, 100.0, 100.0),
        _candle(t0 + 900_000, 101.0, 100.0),
        _candle(t0 + 1_800_000, 101.0, 101.0),
    ]


async def test_runtime_parity_precomputed_with_hand_computed_anchors(
    tmp_path: Path,
) -> None:
    candles = _controlled_candles()
    adapter = _write_tmp_dataset(tmp_path, candles)
    lab = LabSessionRunner(
        adapter=adapter,
        strategy=PrecomputedStrategy([Action.BUY, Action.HOLD, Action.SELL]),
        engine=PaperEngine(config=RISK),
        experiment_spec_id=SPEC_ID,
    ).run()

    # Anclas calculadas a mano (capital 1000, alloc 2% → qty 0.2 @100):
    # fee taker 10bps, slippage 2bps por lado.
    assert [event.action for event in lab.events] == ["BUY", "HOLD", "SELL"]
    assert lab.metrics["fills"] == 2
    assert lab.metrics["fees"] == pytest.approx(0.020004 + 0.02019596)
    assert lab.metrics["slippage_cost"] == pytest.approx(0.004 + 0.00404)
    assert lab.events[0].quantity == pytest.approx(0.2)
    assert lab.events[0].exec_price == pytest.approx(100.02)
    assert lab.events[2].exec_price == pytest.approx(100.9798)
    assert lab.events[2].exit_reason == "llm_sell"

    paper_events = await _run_paper_path(
        candles, PrecomputedStrategy([Action.BUY, Action.HOLD, Action.SELL])
    )
    assert lab.event_trace() == _paper_trace(paper_events)


async def test_runtime_parity_baseline_strategy(tmp_path: Path) -> None:
    t0 = 1_700_000_000_000
    closes = [100.0 + i for i in range(8)] + [107.0 - i for i in range(1, 9)]
    candles = [
        _candle(t0 + i * 900_000, c, closes[i - 1] if i else c) for i, c in enumerate(closes)
    ]
    adapter = _write_tmp_dataset(tmp_path, candles)
    config = EmaRsiConfig(ema_fast=2, ema_slow=4, rsi_period=3, rsi_exit=80.0)

    lab = LabSessionRunner(
        adapter=adapter,
        strategy=EmaRsiBaseline(config),
        engine=PaperEngine(config=RISK),
        experiment_spec_id=SPEC_ID,
    ).run()
    paper_events = await _run_paper_path(candles, EmaRsiBaseline(config))

    assert lab.event_trace() == _paper_trace(paper_events)
    actions = [event.action for event in lab.events]
    assert "HOLD" in actions and any(action != "HOLD" for action in actions)


async def test_risk_rejection_visible_in_both_paths(tmp_path: Path) -> None:
    candles = [_controlled_candles()[0]]
    adapter = _write_tmp_dataset(tmp_path, candles)
    lab = LabSessionRunner(
        adapter=adapter,
        strategy=PrecomputedStrategy([Action.SELL]),
        engine=PaperEngine(config=RISK),
        experiment_spec_id=SPEC_ID,
    ).run()
    assert lab.events[0].filled is False
    assert lab.events[0].risk_reason == "no_position_to_reduce"
    assert lab.metrics["risk_rejections"] == 1

    paper_events = await _run_paper_path(candles, PrecomputedStrategy([Action.SELL]))
    assert lab.event_trace() == _paper_trace(paper_events)


def test_same_input_same_trace_and_metrics(tmp_path: Path) -> None:
    candles = _controlled_candles()
    adapter = _write_tmp_dataset(tmp_path, candles)

    def fresh_run() -> Any:
        return LabSessionRunner(
            adapter=adapter,
            strategy=PrecomputedStrategy([Action.BUY, Action.HOLD, Action.SELL]),
            engine=PaperEngine(config=RISK),
            experiment_spec_id=SPEC_ID,
        ).run()

    first = fresh_run()
    second = fresh_run()
    assert first.event_trace() == second.event_trace()
    assert dict(first.metrics) == dict(second.metrics)
    assert first.event_trace_hash == second.event_trace_hash
    assert first.metrics_hash_value == second.metrics_hash_value


def test_run_linked_to_experiment_spec(tmp_path: Path) -> None:
    adapter = _write_tmp_dataset(tmp_path, _controlled_candles())
    spec = ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": 0,
            "row_end": 3,
        },
        strategy={"name": "precomputed", "version": "precomputed"},
        risk={"version": "risk-v1", "capital": 1000.0},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )
    linked_id = spec_id(spec)
    result = LabSessionRunner(
        adapter=adapter,
        strategy=PrecomputedStrategy([Action.BUY, Action.HOLD, Action.SELL]),
        engine=PaperEngine(config=RISK),
        experiment_spec_id=linked_id,
    ).run()
    assert result.experiment_spec_id == linked_id
    run = ExperimentRun(
        experiment_spec_id=linked_id,
        run_id="17d-test-run-1",
        created_at="2026-09-12T00:00:00+00:00",
        application_git_sha="96998e6",
        status="ok",
        event_trace_hash=result.event_trace_hash,
        metrics_hash=result.metrics_hash_value,
    )
    assert run.experiment_spec_id == linked_id


def test_real_frozen_development_range_runs() -> None:
    adapter = FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=0, row_end=64
    )
    result = LabSessionRunner(
        adapter=adapter,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=RiskConfig()),
        experiment_spec_id=SPEC_ID,
    ).run()
    assert len(result.events) == 64
    assert result.metrics["candles"] == 64
    assert result.experiment_spec_id == SPEC_ID


def test_invalid_spec_id_rejected(tmp_path: Path) -> None:
    adapter = _write_tmp_dataset(tmp_path, _controlled_candles())
    with pytest.raises(ValueError, match="experiment_spec_id"):
        LabSessionRunner(
            adapter=adapter,
            strategy=PrecomputedStrategy([Action.HOLD]),
            engine=PaperEngine(config=RISK),
            experiment_spec_id="not-a-hash",
        )


def test_summarize_is_pure_and_deterministic(tmp_path: Path) -> None:
    adapter = _write_tmp_dataset(tmp_path, _controlled_candles())
    result = LabSessionRunner(
        adapter=adapter,
        strategy=PrecomputedStrategy([Action.BUY, Action.HOLD, Action.SELL]),
        engine=PaperEngine(config=RISK),
        experiment_spec_id=SPEC_ID,
    ).run()
    again = summarize_lab_events(result.events, initial_equity=1000.0)
    assert again == dict(result.metrics)
