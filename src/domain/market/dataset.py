"""Modelo del dataset congelado y su manifest (PRD §40–41)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CandleFileEntry:
    symbol: str
    timeframe: str
    path: str
    row_count: int
    sha256: str
    start_ms: int
    end_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "path": self.path,
            "row_count": self.row_count,
            "sha256": self.sha256,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandleFileEntry:
        return cls(
            symbol=str(data["symbol"]),
            timeframe=str(data["timeframe"]),
            path=str(data["path"]),
            row_count=int(data["row_count"]),
            sha256=str(data["sha256"]),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
        )


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_version: str
    source: str
    schema_version: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    downloaded_at: str
    download_command: str
    files: tuple[CandleFileEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "source": self.source,
            "schema_version": self.schema_version,
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "downloaded_at": self.downloaded_at,
            "download_command": self.download_command,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetManifest:
        return cls(
            dataset_version=str(data["dataset_version"]),
            source=str(data["source"]),
            schema_version=str(data["schema_version"]),
            symbols=tuple(str(s) for s in data["symbols"]),
            timeframes=tuple(str(t) for t in data["timeframes"]),
            downloaded_at=str(data["downloaded_at"]),
            download_command=str(data["download_command"]),
            files=tuple(CandleFileEntry.from_dict(f) for f in data["files"]),
        )
