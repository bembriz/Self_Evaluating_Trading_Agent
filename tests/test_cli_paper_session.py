"""Tests del subcomando CLI `paper-session` (sesión paper evaluada sobre dataset congelado)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.market.candle import Candle
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.paper_session import run_paper_session


def _series(n: int, start: float = 100.0) -> list[Candle]:
    return [
        Candle(
            timestamp_ms=i * 900_000,
            open=start + i * 0.5,
            high=start + i * 0.5 + 2.0,
            low=start + i * 0.5 - 1.0,
            close=start + i * 0.5 + 1.5,
            volume=10.0,
            turnover=1000.0,
        )
        for i in range(n)
    ]


@pytest.fixture()
def frozen_dataset(tmp_path: Path) -> tuple[Path, Path]:
    store = LocalDatasetStore()
    csv_path = tmp_path / "datasets" / "TEST_V001" / "ETHUSDT_15m.csv"
    candles = _series(300)
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


def test_paper_session_writes_evaluated_metrics(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, _ = frozen_dataset
    output = tmp_path / "paper_session.json"
    code = run_paper_session(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--output", str(output)],
    )
    assert code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["session"]["bars"] == 300
    assert sum(payload["session"]["decisions"].values()) == 300
    for key in ("filled", "rejected", "kill_switch_tripped"):
        assert key in payload["session"]
    m = payload["metrics"]
    assert m["fees"] >= 0.0
    assert m["slippage"] >= 0.0
    assert m["llm_cost"] == 0.0
    assert "fully_loaded_pnl" in m
    assert payload["risk_config"]["version"] == "risk-v1"
    assert payload["benchmark_buy_hold"]["strategy_version"] == "buy-and-hold"


def test_paper_session_aborts_on_corrupted_dataset(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, csv_path = frozen_dataset
    csv_path.write_text("timestamp_ms,open\n1,2\n", encoding="utf-8")
    output = tmp_path / "paper_session.json"
    code = run_paper_session(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--output", str(output)],
    )
    assert code == 1
    assert not output.exists()


def test_paper_session_is_deterministic(frozen_dataset: tuple[Path, Path], tmp_path: Path) -> None:
    manifest_path, _ = frozen_dataset
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    assert (
        run_paper_session(
            store=LocalDatasetStore(), manifest_path=manifest_path, argv=["--output", str(out_a)]
        )
        == 0
    )
    assert (
        run_paper_session(
            store=LocalDatasetStore(), manifest_path=manifest_path, argv=["--output", str(out_b)]
        )
        == 0
    )
    assert out_a.read_bytes() == out_b.read_bytes()


def test_paper_session_rejects_unknown_timeframe(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, _ = frozen_dataset
    output = tmp_path / "paper_session.json"
    code = run_paper_session(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--timeframe", "7m", "--output", str(output)],
    )
    assert code == 2
