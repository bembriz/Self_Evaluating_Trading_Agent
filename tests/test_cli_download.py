from pathlib import Path

import pytest
from pytest import CaptureFixture

from domain.market.candle import Candle, Timeframe
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.storage.dataset_store import LocalDatasetStore
from interfaces.cli.download import (
    _months_ago_ms,
    _now_ms,
    _parse_timeframes,
    verify_manifest,
)


def test_months_ago_ms_is_int() -> None:
    assert isinstance(_months_ago_ms(36), int)


def test_now_ms_is_int() -> None:
    assert isinstance(_now_ms(), int)


def test_parse_timeframes() -> None:
    assert _parse_timeframes(["15m", "1h", "4h"]) == (
        Timeframe.M15,
        Timeframe.H1,
        Timeframe.H4,
    )


def test_parse_timeframes_unknown_raises() -> None:
    with pytest.raises(ValueError):
        _parse_timeframes(["5m"])


def test_verify_manifest_ok(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    store = LocalDatasetStore()
    candles = [Candle(0, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)]
    csv_path = tmp_path / "ETHUSDT_15m.csv"
    store.write_candles(csv_path, candles)
    entry = CandleFileEntry(
        symbol="ETHUSDT",
        timeframe="15m",
        path=str(csv_path),
        row_count=1,
        sha256=store.compute_sha256(csv_path),
        start_ms=0,
        end_ms=0,
    )
    manifest = DatasetManifest(
        dataset_version="V001",
        source="s",
        schema_version="1.0",
        symbols=("ETHUSDT",),
        timeframes=("15m",),
        downloaded_at="d",
        download_command="c",
        files=(entry,),
    )
    manifest_path = tmp_path / "manifest.json"
    store.write_manifest(manifest, manifest_path)

    assert verify_manifest(store, manifest_path) == 0
    assert "OK " in capsys.readouterr().out


def test_verify_manifest_bad_checksum(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    store = LocalDatasetStore()
    csv_path = tmp_path / "ETHUSDT_15m.csv"
    store.write_candles(csv_path, [Candle(0, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)])
    entry = CandleFileEntry("ETHUSDT", "15m", str(csv_path), 1, "0" * 64, 0, 0)
    manifest = DatasetManifest(
        dataset_version="V001",
        source="s",
        schema_version="1.0",
        symbols=("ETHUSDT",),
        timeframes=("15m",),
        downloaded_at="d",
        download_command="c",
        files=(entry,),
    )
    manifest_path = tmp_path / "manifest.json"
    store.write_manifest(manifest, manifest_path)

    assert verify_manifest(store, manifest_path) == 1
    assert "BAD" in capsys.readouterr().out
