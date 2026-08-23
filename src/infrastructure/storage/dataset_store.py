"""Persistencia del dataset congelado en archivos (CSV + manifest + SHA-256)."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from domain.market.candle import Candle
from domain.market.dataset import DatasetManifest

HEADER = ["timestamp_ms", "open", "high", "low", "close", "volume", "turnover"]


class LocalDatasetStore:
    def write_candles(self, path: Path, candles: list[Candle]) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(HEADER)
            for c in candles:
                writer.writerow(
                    [c.timestamp_ms, c.open, c.high, c.low, c.close, c.volume, c.turnover]
                )
        return len(candles)

    def read_candles(self, path: Path) -> list[Candle]:
        candles: list[Candle] = []
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                candles.append(
                    Candle(
                        timestamp_ms=int(row["timestamp_ms"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                        turnover=float(row["turnover"]),
                    )
                )
        return candles

    def compute_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def write_manifest(self, manifest: DatasetManifest, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def read_manifest(self, path: Path) -> DatasetManifest:
        return DatasetManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
