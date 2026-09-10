from pathlib import Path

import pytest

from application.services.historical_data import HistoricalDataService, IngestRequest
from domain.market.candle import Candle, Timeframe
from domain.market.dataset import DatasetManifest


class FakeClient:
    def __init__(self, candles: dict[tuple[str, Timeframe], list[Candle]]) -> None:
        self._candles = candles

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return self._candles[(symbol, interval)]


class FakeStore:
    def __init__(self) -> None:
        self.manifests: list[tuple[DatasetManifest, Path]] = []

    def write_candles(self, path: Path, candles: list[Candle]) -> int:
        return len(candles)

    def read_candles(self, path: Path) -> list[Candle]:
        return []

    def compute_sha256(self, path: Path) -> str:
        return "a" * 64

    def write_manifest(self, manifest: DatasetManifest, path: Path) -> None:
        self.manifests.append((manifest, path))

    def read_manifest(self, path: Path) -> DatasetManifest:
        raise NotImplementedError


class FakeCandleRepo:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, Timeframe, int]] = []

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        self.upserts.append((symbol, timeframe, len(candles)))
        return len(candles)

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        return 0

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def upsert_paper(
        self, session_id: str, symbol: str, timeframe: Timeframe, candles: list[Candle]
    ) -> int:
        return len(candles)

    async def session_range(
        self, session_id: str, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        return []

    async def last_persisted_ms(
        self, session_id: str, symbol: str, timeframe: Timeframe
    ) -> int | None:
        return None


class FakeManifestRepo:
    def __init__(self) -> None:
        self.saved: list[DatasetManifest] = []

    async def upsert(self, manifest: DatasetManifest) -> None:
        self.saved.append(manifest)

    async def get(self, version: str) -> DatasetManifest | None:
        return None


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)


def make_service() -> HistoricalDataService:
    return HistoricalDataService(
        client=FakeClient({("ETHUSDT", Timeframe.M15): [mk(0), mk(15 * 60_000)]}),
        store=FakeStore(),
        candle_repo=FakeCandleRepo(),
        manifest_repo=FakeManifestRepo(),
    )


def make_request(tmp_path: Path) -> IngestRequest:
    return IngestRequest(
        dataset_version="V001",
        symbols=("ETHUSDT",),
        timeframes=(Timeframe.M15,),
        start_ms=0,
        end_ms=15 * 60_000,
        data_dir=tmp_path,
        manifest_path=tmp_path / "manifest.json",
        download_command="cmd",
    )


async def test_ingest_happy_path(tmp_path: Path) -> None:
    svc = make_service()
    report = await svc.ingest(make_request(tmp_path))
    assert report.dataset_version == "V001"
    assert len(report.files) == 1
    f = report.files[0]
    assert f.sha256 == "a" * 64
    assert f.row_count == 2
    assert f.warnings == ()
    assert report.manifest.dataset_version == "V001"
    assert report.manifest.files[0].sha256 == "a" * 64


async def test_ingest_aborts_on_validation_error(tmp_path: Path) -> None:
    svc = HistoricalDataService(
        client=FakeClient({("ETHUSDT", Timeframe.M15): [mk(15 * 60_000), mk(0)]}),
        store=FakeStore(),
        candle_repo=FakeCandleRepo(),
        manifest_repo=FakeManifestRepo(),
    )
    with pytest.raises(ValueError):
        await svc.ingest(make_request(tmp_path))
