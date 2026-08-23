from domain.market.dataset import CandleFileEntry, DatasetManifest


def test_file_entry_roundtrip() -> None:
    e = CandleFileEntry("ETHUSDT", "15m", "datasets/V001/ETHUSDT_15m.csv", 12, "abc", 1, 2)
    d = e.to_dict()
    assert CandleFileEntry.from_dict(d) == e


def test_manifest_roundtrip() -> None:
    m = DatasetManifest(
        dataset_version="BYBIT_ETHBTC_V001",
        source="Bybit REST v5 /v5/market/kline (spot)",
        schema_version="1.0",
        symbols=("ETHUSDT", "BTCUSDT"),
        timeframes=("15m", "1h", "4h"),
        downloaded_at="2026-08-23T00:00:00+00:00",
        download_command="python -m main download ...",
        files=(CandleFileEntry("ETHUSDT", "15m", "p", 12, "abc", 1, 2),),
    )
    assert DatasetManifest.from_dict(m.to_dict()) == m
