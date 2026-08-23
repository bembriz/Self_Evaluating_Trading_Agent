from pathlib import Path

from domain.market.candle import Candle
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.storage.dataset_store import LocalDatasetStore

STORE = LocalDatasetStore()


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.5, 150.0)


def test_csv_roundtrip(tmp_path: Path) -> None:
    candles = [mk(0), mk(15 * 60_000)]
    path = tmp_path / "ETHUSDT_15m.csv"
    n = STORE.write_candles(path, candles)
    assert n == 2
    assert STORE.read_candles(path) == candles


def test_sha256_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "f.csv"
    STORE.write_candles(path, [mk(0)])
    assert STORE.compute_sha256(path) == STORE.compute_sha256(path)
    assert len(STORE.compute_sha256(path)) == 64


def test_manifest_roundtrip_file(tmp_path: Path) -> None:
    m = DatasetManifest(
        dataset_version="V001",
        source="s",
        schema_version="1.0",
        symbols=("ETHUSDT",),
        timeframes=("15m",),
        downloaded_at="d",
        download_command="c",
        files=(CandleFileEntry("ETHUSDT", "15m", "p", 1, "abc", 0, 0),),
    )
    path = tmp_path / "manifest.json"
    STORE.write_manifest(m, path)
    assert STORE.read_manifest(path) == m
