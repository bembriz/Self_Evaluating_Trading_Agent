"""Tests del subcomando CLI `backtest` (corrida oficial sobre dataset congelado)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.market.candle import Candle
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.backtest import run_backtest


def _rising(n: int, start: float = 100.0) -> list[Candle]:
    return [
        Candle(
            timestamp_ms=i * 900_000,
            open=start + i * 0.5,
            high=start + i * 0.5 + 1.5,
            low=start + i * 0.5,
            close=start + i * 0.5 + 1.5,
            volume=10.0,
            turnover=1000.0,
        )
        for i in range(n)
    ]


@pytest.fixture()
def frozen_dataset(tmp_path: Path) -> tuple[Path, Path]:
    """Dataset congelado mínimo (ETHUSDT 15m) con manifest consistente."""
    store = LocalDatasetStore()
    data_dir = tmp_path / "datasets" / "TEST_V001"
    csv_path = data_dir / "ETHUSDT_15m.csv"
    candles = _rising(300)
    store.write_candles(csv_path, candles)
    entry = CandleFileEntry(
        symbol="ETHUSDT",
        timeframe="15m",
        path=str(csv_path),
        row_count=len(candles),
        sha256=store.compute_sha256(csv_path),
        start_ms=candles[0].timestamp_ms,
        end_ms=candles[-1].timestamp_ms,
    )
    manifest = DatasetManifest(
        dataset_version="TEST_V001",
        source="test",
        schema_version="1.0",
        symbols=("ETHUSDT",),
        timeframes=("15m",),
        downloaded_at="2026-08-25T00:00:00+00:00",
        download_command="test",
        files=(entry,),
    )
    manifest_path = tmp_path / "manifest.json"
    store.write_manifest(manifest, manifest_path)
    return manifest_path, csv_path


def test_run_backtest_writes_metrics_and_benchmark(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, _ = frozen_dataset
    output = tmp_path / "backtest_result.json"
    code = run_backtest(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--output", str(output)],
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    metrics = payload["metrics"]
    for key in (
        "gross_pnl",
        "net_pnl",
        "fully_loaded_pnl",
        "win_rate",
        "loss_rate",
        "profit_factor",
        "sharpe",
        "sortino",
        "max_drawdown",
        "expectancy",
        "avg_winner",
        "avg_loser",
        "risk_reward",
        "fees",
        "slippage",
        "llm_cost",
        "trades",
        "avg_holding_bars",
        "exposure",
    ):
        assert key in metrics, key
    assert payload["benchmark_buy_hold"]["strategy_version"] == "buy-and-hold"
    assert payload["dataset"]["version"] == "TEST_V001"
    assert payload["params"]["initial_cash"] > 0
    assert payload["signals"] >= 0


def test_run_backtest_aborts_on_corrupted_dataset(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, csv_path = frozen_dataset
    csv_path.write_text("timestamp_ms,open\n1,2\n", encoding="utf-8")
    output = tmp_path / "backtest_result.json"
    code = run_backtest(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--output", str(output)],
    )
    assert code == 1
    assert not output.exists()


def test_run_backtest_is_deterministic(frozen_dataset: tuple[Path, Path], tmp_path: Path) -> None:
    manifest_path, _ = frozen_dataset
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    argv_a = ["--output", str(out_a)]
    argv_b = ["--output", str(out_b)]
    assert run_backtest(store=LocalDatasetStore(), manifest_path=manifest_path, argv=argv_a) == 0
    assert run_backtest(store=LocalDatasetStore(), manifest_path=manifest_path, argv=argv_b) == 0
    assert out_a.read_bytes() == out_b.read_bytes()


def test_run_backtest_rejects_unknown_timeframe(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, _ = frozen_dataset
    output = tmp_path / "backtest_result.json"
    code = run_backtest(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--timeframe", "7m", "--output", str(output)],
    )
    assert code == 2
