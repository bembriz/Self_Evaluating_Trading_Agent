"""Tests del subcomando CLI `replay` (replay determinista de decisiones históricas)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from domain.market.candle import Candle
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.replay import run_replay


def _series(n: int, start: float = 100.0) -> list[Candle]:
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


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_run_replay_writes_decision_trace(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, _ = frozen_dataset
    output = tmp_path / "replay_trace.jsonl"
    code = run_replay(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--output", str(output)],
    )
    assert code == 0
    records = _records(output)
    assert records[0]["type"] == "header"
    assert records[0]["dataset"]["version"] == "TEST_V001"
    assert records[0]["strategy"]["version"] == "baseline-v1"
    assert records[-1]["type"] == "summary"
    decisions = [r for r in records if r["type"] == "decision"]
    assert len(decisions) == 300
    summary = records[-1]
    assert summary["bars"] == 300
    assert summary["buy"] + summary["sell"] + summary["hold"] == 300
    for d in decisions[:5]:
        assert d["action"] == "hold"


def test_run_replay_aborts_on_corrupted_dataset(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, csv_path = frozen_dataset
    csv_path.write_text("timestamp_ms,open\n1,2\n", encoding="utf-8")
    output = tmp_path / "replay_trace.jsonl"
    code = run_replay(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--output", str(output)],
    )
    assert code == 1
    assert not output.exists()


def test_run_replay_is_deterministic(frozen_dataset: tuple[Path, Path], tmp_path: Path) -> None:
    manifest_path, _ = frozen_dataset
    out_a = tmp_path / "a.jsonl"
    out_b = tmp_path / "b.jsonl"
    assert (
        run_replay(
            store=LocalDatasetStore(), manifest_path=manifest_path, argv=["--output", str(out_a)]
        )
        == 0
    )
    assert (
        run_replay(
            store=LocalDatasetStore(), manifest_path=manifest_path, argv=["--output", str(out_b)]
        )
        == 0
    )
    assert out_a.read_bytes() == out_b.read_bytes()


def test_run_replay_rejects_unknown_timeframe(
    frozen_dataset: tuple[Path, Path], tmp_path: Path
) -> None:
    manifest_path, _ = frozen_dataset
    output = tmp_path / "replay_trace.jsonl"
    code = run_replay(
        store=LocalDatasetStore(),
        manifest_path=manifest_path,
        argv=["--timeframe", "7m", "--output", str(output)],
    )
    assert code == 2
