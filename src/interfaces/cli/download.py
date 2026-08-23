"""Subcomandos de ingesta y verificación del dataset histórico."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from application.ports.dataset_store import DatasetStore
from application.services.historical_data import HistoricalDataService, IngestRequest
from domain.market.candle import Timeframe
from infrastructure.bybit.client import BybitRestClient
from infrastructure.database.repositories import (
    SqlAlchemyDatasetManifestRepository,
    SqlAlchemyMarketCandleRepository,
)
from infrastructure.database.session import build_session_factory, create_engine
from infrastructure.storage.dataset_store import LocalDatasetStore
from settings import Settings

DEFAULT_DATASET = "BYBIT_ETHBTC_V001"


def _months_ago_ms(months: int) -> int:
    start = datetime.now(UTC) - timedelta(days=30 * months)
    return int(start.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _parse_timeframes(labels: list[str]) -> tuple[Timeframe, ...]:
    return tuple(Timeframe.from_label(label) for label in labels)


async def _download(settings: Settings, args: argparse.Namespace) -> int:
    engine = create_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    session = session_factory()
    client = BybitRestClient(
        base_url=settings.bybit_base_url, timeout=settings.bybit_request_timeout
    )
    try:
        timeframes = _parse_timeframes(args.timeframes)
        start_ms = args.start_ms if args.start_ms is not None else _months_ago_ms(args.months)
        end_ms = args.end_ms if args.end_ms is not None else _now_ms()
        data_dir = Path(settings.dataset_dir) / args.dataset_version
        manifest_path = Path("docs") / "datasets" / f"{args.dataset_version}.manifest.json"
        service = HistoricalDataService(
            client=client,
            store=LocalDatasetStore(),
            candle_repo=SqlAlchemyMarketCandleRepository(session),
            manifest_repo=SqlAlchemyDatasetManifestRepository(session),
        )
        request = IngestRequest(
            dataset_version=args.dataset_version,
            symbols=tuple(args.symbols),
            timeframes=timeframes,
            start_ms=start_ms,
            end_ms=end_ms,
            data_dir=data_dir,
            manifest_path=manifest_path,
            download_command=" ".join(["python", "-m", "main"] + sys.argv[1:]),
        )
        report = await service.ingest(request)
        await session.commit()
        print(
            json.dumps(
                {
                    "dataset_version": report.dataset_version,
                    "files": [
                        {
                            "symbol": f.symbol,
                            "timeframe": f.timeframe.label,
                            "rows": f.row_count,
                            "sha256": f.sha256,
                            "warnings": list(f.warnings),
                        }
                        for f in report.files
                    ],
                },
                indent=2,
            )
        )
        return 0
    finally:
        await session.close()
        await engine.dispose()
        await client.close()


async def _verify(settings: Settings, args: argparse.Namespace) -> int:
    del settings
    store = LocalDatasetStore()
    manifest_path = Path("docs") / "datasets" / f"{args.dataset_version}.manifest.json"
    return verify_manifest(store, manifest_path)


def verify_manifest(store: DatasetStore, manifest_path: Path) -> int:
    """Recomputa SHA-256 y recuenta filas para cada archivo del manifest."""
    manifest = store.read_manifest(manifest_path)
    ok = True
    for entry in manifest.files:
        path = Path(entry.path)
        digest = store.compute_sha256(path)
        candles = store.read_candles(path)
        valid = digest == entry.sha256 and len(candles) == entry.row_count
        if not valid:
            ok = False
        print(f"{'OK ' if valid else 'BAD'} {entry.path} rows={len(candles)} sha256={digest[:12]}…")
    return 0 if ok else 1


def download(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="download")
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    parser.add_argument("--symbols", nargs="+", default=["ETHUSDT", "BTCUSDT"])
    parser.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h"])
    parser.add_argument("--months", type=int, default=36)
    parser.add_argument("--start-ms", type=int, default=None)
    parser.add_argument("--end-ms", type=int, default=None)
    args = parser.parse_args(argv)
    return asyncio.run(_download(Settings(), args))


def verify(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="verify")
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    args = parser.parse_args(argv)
    return asyncio.run(_verify(Settings(), args))
