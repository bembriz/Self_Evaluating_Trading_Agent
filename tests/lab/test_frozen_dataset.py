"""Tests fase 17D: FrozenDatasetAdapter — holdout safety y validación.

Solo lectura del dataset oficial congelado. Sin estrategias, sin backtest,
sin métricas sobre FINAL_HOLDOUT (solo se verifica su bloqueo).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from lab.frozen_dataset import FrozenDatasetAdapter

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "docs/datasets/BYBIT_ETHBTC_V001.manifest.json"
CSV = REPO / "datasets/BYBIT_ETHBTC_V001" / "ETHUSDT_15m.csv"
HOLDOUT_STATE = REPO / "holdout" / "v1.state.json"

EXPECTED_SHA = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()


def open_repo_range(row_start: int, row_end: int) -> FrozenDatasetAdapter:
    return FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=row_start, row_end=row_end
    )


def test_development_range_allowed() -> None:
    adapter = open_repo_range(0, 96)
    assert len(adapter) == 96
    assert adapter.range.row_start == 0
    assert adapter.range.row_end == 96


def test_walk_forward_range_allowed() -> None:
    adapter = open_repo_range(62208, 62304)
    assert len(adapter) == 96
    assert adapter.range.row_start == 62208


def test_final_holdout_rejected() -> None:
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        open_repo_range(88128, 103680)


def test_crossing_into_holdout_rejected() -> None:
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        open_repo_range(88000, 89000)


def test_wrong_manifest_sha_rejected() -> None:
    with pytest.raises(ValueError, match="manifest SHA mismatch"):
        FrozenDatasetAdapter(
            dataset_id="BYBIT_ETHBTC_V001",
            symbol="ETHUSDT",
            timeframe="15m",
            manifest_path=MANIFEST,
            csv_path=CSV,
            expected_manifest_sha="0" * 64,
            row_start=0,
            row_end=96,
        )


def test_wrong_dataset_id_rejected() -> None:
    with pytest.raises(ValueError, match="dataset_id mismatch"):
        FrozenDatasetAdapter(
            dataset_id="WRONG_DATASET",
            symbol="ETHUSDT",
            timeframe="15m",
            manifest_path=MANIFEST,
            csv_path=CSV,
            expected_manifest_sha=EXPECTED_SHA,
            row_start=0,
            row_end=96,
        )


def test_unknown_symbol_rejected() -> None:
    with pytest.raises(ValueError, match="no manifest entry"):
        FrozenDatasetAdapter(
            dataset_id="BYBIT_ETHBTC_V001",
            symbol="NOPE",
            timeframe="15m",
            manifest_path=MANIFEST,
            csv_path=CSV,
            expected_manifest_sha=EXPECTED_SHA,
            row_start=0,
            row_end=96,
        )


def test_out_of_order_timestamps_rejected(tmp_path: Path) -> None:
    rows = [
        {
            "timestamp_ms": "3000",
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "1",
            "turnover": "1",
        },
        {
            "timestamp_ms": "1000",
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "1",
            "turnover": "1",
        },
        {
            "timestamp_ms": "2000",
            "open": "1",
            "high": "1",
            "low": "1",
            "close": "1",
            "volume": "1",
            "turnover": "1",
        },
    ]
    csv_path = tmp_path / "X_15m.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "dataset_version": "TMP",
        "files": [
            {
                "symbol": "X",
                "timeframe": "15m",
                "row_count": 3,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "start_ms": 3000,
                "end_ms": 2000,
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="out-of-order"):
        FrozenDatasetAdapter(
            dataset_id="TMP",
            symbol="X",
            timeframe="15m",
            manifest_path=manifest_path,
            csv_path=csv_path,
            expected_manifest_sha=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            row_start=0,
            row_end=3,
        )


def _write_tmp_manifest(
    tmp_path: Path,
    csv_path: Path,
    *,
    dataset_version: str = "BYBIT_ETHBTC_V001",
    symbol: str = "ETHUSDT",
    timeframe: str = "15m",
    row_count: int | None = None,
    csv_sha: str | None = None,
    with_files_section: bool = True,
) -> tuple[Path, str]:
    rows = list(csv_path.read_text(encoding="utf-8").splitlines())
    manifest: dict[str, object] = {"dataset_version": dataset_version}
    if with_files_section:
        manifest["files"] = [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "row_count": len(rows) - 1 if row_count is None else row_count,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()
                if csv_sha is None
                else csv_sha,
                "start_ms": 1000,
                "end_ms": 2000,
            }
        ]
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return manifest_path, expected


def _write_tmp_csv(tmp_path: Path, n_rows: int = 3) -> Path:
    csv_path = tmp_path / "ETHUSDT_15m.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_ms", "open", "high", "low", "close", "volume", "turnover"])
        for i in range(n_rows):
            ts = 1000 + i * 900_000
            writer.writerow([ts, "1", "1", "1", "1", "1", "1"])
    return csv_path


def _open_tmp(
    tmp_path: Path,
    csv_path: Path,
    manifest_path: Path,
    expected: str,
    row_start: int = 0,
    row_end: int = 3,
    **overrides: Any,
) -> FrozenDatasetAdapter:
    params: dict[str, Any] = {
        "dataset_id": "BYBIT_ETHBTC_V001",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "manifest_path": manifest_path,
        "csv_path": csv_path,
        "expected_manifest_sha": expected,
        "row_start": row_start,
        "row_end": row_end,
    }
    params.update(overrides)
    return FrozenDatasetAdapter(**params)


def test_candles_preserve_exact_ohlcv() -> None:
    adapter = open_repo_range(0, 96)
    with open(CSV, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[:96]
    assert len(adapter.candles) == len(rows)
    for candle, row in zip(adapter.candles, rows, strict=True):
        assert candle.timestamp_ms == int(row["timestamp_ms"])
        assert candle.open == float(row["open"])
        assert candle.high == float(row["high"])
        assert candle.low == float(row["low"])
        assert candle.close == float(row["close"])
        assert candle.volume == float(row["volume"])
        assert candle.turnover == float(row["turnover"])
    stamps = [candle.timestamp_ms for candle in adapter.candles]
    assert stamps == sorted(stamps)


def test_holdout_state_stays_pristine() -> None:
    state = json.loads(HOLDOUT_STATE.read_text(encoding="utf-8"))
    assert state["state"] == "PRISTINE"
    assert state["split_version"] == 1


def test_bool_bounds_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path)
    with pytest.raises(ValueError, match="must be integers"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected, **{"row_start": True})
    with pytest.raises(ValueError, match="must be integers"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected, **{"row_end": True})


def test_non_integer_bounds_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path)
    bad: dict[str, Any] = {"row_start": "0"}
    with pytest.raises(ValueError, match="must be integers"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected, **bad)


def test_invalid_range_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path)
    with pytest.raises(ValueError, match="invalid range"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected, row_start=-1, row_end=3)
    with pytest.raises(ValueError, match="invalid range"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected, row_start=2, row_end=2)


def test_missing_manifest_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path)
    with pytest.raises(ValueError, match="manifest not found"):
        FrozenDatasetAdapter(
            dataset_id="BYBIT_ETHBTC_V001",
            symbol="ETHUSDT",
            timeframe="15m",
            manifest_path=tmp_path / "absent.json",
            csv_path=csv_path,
            expected_manifest_sha="0" * 64,
            row_start=0,
            row_end=3,
        )


def test_missing_csv_rejected() -> None:
    with pytest.raises(ValueError, match="csv not found"):
        FrozenDatasetAdapter(
            dataset_id="BYBIT_ETHBTC_V001",
            symbol="ETHUSDT",
            timeframe="15m",
            manifest_path=MANIFEST,
            csv_path=REPO / "datasets" / "BYBIT_ETHBTC_V001" / "ABSENT.csv",
            expected_manifest_sha=EXPECTED_SHA,
            row_start=0,
            row_end=96,
        )


def test_csv_sha_mismatch_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path, csv_sha="1" * 64)
    with pytest.raises(ValueError, match="csv SHA mismatch"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected)


def test_row_count_mismatch_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path, n_rows=3)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path, row_count=99)
    with pytest.raises(ValueError, match="row count mismatch"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected)


def test_range_end_beyond_rows_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path, n_rows=3)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path)
    with pytest.raises(ValueError, match="beyond dataset rows"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected, row_start=0, row_end=99)


def test_manifest_without_files_rejected(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path, with_files_section=False)
    with pytest.raises(ValueError, match="no files section"):
        _open_tmp(tmp_path, csv_path, manifest_path, expected)


def test_manifest_with_non_dict_entry_skipped(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path, n_rows=3)
    manifest = {
        "dataset_version": "BYBIT_ETHBTC_V001",
        "files": [
            "not-a-dict",
            {
                "symbol": "OTHER",
                "timeframe": "1h",
                "row_count": 3,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "start_ms": 1000,
                "end_ms": 2000,
            },
            {
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "row_count": 3,
                "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "start_ms": 1000,
                "end_ms": 2000,
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    adapter = _open_tmp(tmp_path, csv_path, manifest_path, expected)
    assert len(adapter) == 3


def test_adapter_iterates_candles_in_order(tmp_path: Path) -> None:
    csv_path = _write_tmp_csv(tmp_path, n_rows=4)
    manifest_path, expected = _write_tmp_manifest(tmp_path, csv_path)
    adapter = _open_tmp(tmp_path, csv_path, manifest_path, expected, row_start=0, row_end=4)
    assert [candle.timestamp_ms for candle in adapter] == [
        candle.timestamp_ms for candle in adapter.candles
    ]
    assert adapter.range.symbol == "ETHUSDT"
    assert adapter.range.timeframe == "15m"
