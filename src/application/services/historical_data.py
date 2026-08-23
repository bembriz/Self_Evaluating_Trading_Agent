"""Orquestación de la ingesta histórica (PRD §40: download→validate→persist→checksum→reload)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from application.ports.dataset_store import DatasetStore
from application.ports.market_data import MarketDataClient
from application.ports.market_repositories import (
    DatasetManifestRepository,
    MarketCandleRepository,
)
from application.services.validation import validate_candles
from domain.market.candle import Timeframe
from domain.market.dataset import CandleFileEntry, DatasetManifest

SCHEMA_VERSION = "1.0"
SOURCE = "Bybit REST v5 /v5/market/kline (spot)"


@dataclass(frozen=True, slots=True)
class IngestRequest:
    dataset_version: str
    symbols: tuple[str, ...]
    timeframes: tuple[Timeframe, ...]
    start_ms: int
    end_ms: int
    data_dir: Path
    manifest_path: Path
    download_command: str


@dataclass(frozen=True, slots=True)
class IngestFileResult:
    symbol: str
    timeframe: Timeframe
    path: str
    row_count: int
    sha256: str
    start_ms: int
    end_ms: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IngestReport:
    dataset_version: str
    files: tuple[IngestFileResult, ...]
    manifest: DatasetManifest


class HistoricalDataService:
    def __init__(
        self,
        client: MarketDataClient,
        store: DatasetStore,
        candle_repo: MarketCandleRepository,
        manifest_repo: DatasetManifestRepository,
    ) -> None:
        self._client = client
        self._store = store
        self._candle_repo = candle_repo
        self._manifest_repo = manifest_repo

    async def ingest(self, request: IngestRequest) -> IngestReport:
        entries: list[CandleFileEntry] = []
        file_results: list[IngestFileResult] = []

        for symbol in request.symbols:
            for timeframe in request.timeframes:
                candles = await self._client.fetch_candles(
                    symbol, timeframe, request.start_ms, request.end_ms
                )
                result = validate_candles(candles, timeframe)
                if result.errors:
                    raise ValueError(f"{symbol} {timeframe.label}: {result.errors}")

                rel_path = str(request.data_dir / f"{symbol}_{timeframe.label}.csv")
                abs_path = request.data_dir / f"{symbol}_{timeframe.label}.csv"
                self._store.write_candles(abs_path, candles)
                sha256 = self._store.compute_sha256(abs_path)
                await self._candle_repo.upsert(symbol, timeframe, candles)

                file_results.append(
                    IngestFileResult(
                        symbol=symbol,
                        timeframe=timeframe,
                        path=rel_path,
                        row_count=len(candles),
                        sha256=sha256,
                        start_ms=candles[0].timestamp_ms if candles else request.start_ms,
                        end_ms=candles[-1].timestamp_ms if candles else request.end_ms,
                        warnings=result.warnings,
                    )
                )
                entries.append(
                    CandleFileEntry(
                        symbol=symbol,
                        timeframe=timeframe.label,
                        path=rel_path,
                        row_count=len(candles),
                        sha256=sha256,
                        start_ms=candles[0].timestamp_ms if candles else request.start_ms,
                        end_ms=candles[-1].timestamp_ms if candles else request.end_ms,
                    )
                )

        manifest = DatasetManifest(
            dataset_version=request.dataset_version,
            source=SOURCE,
            schema_version=SCHEMA_VERSION,
            symbols=request.symbols,
            timeframes=tuple(t.label for t in request.timeframes),
            downloaded_at=datetime.now(UTC).isoformat(),
            download_command=request.download_command,
            files=tuple(entries),
        )
        self._store.write_manifest(manifest, request.manifest_path)
        await self._manifest_repo.upsert(manifest)

        return IngestReport(
            dataset_version=request.dataset_version,
            files=tuple(file_results),
            manifest=manifest,
        )
