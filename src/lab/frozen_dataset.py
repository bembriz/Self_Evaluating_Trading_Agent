"""FrozenDatasetAdapter: lectura validada del dataset oficial congelado (Fase 17D).

Responsabilidad única: exponer velas OHLCV originales en orden temporal para un
rango [start, end) de DEVELOPMENT o WALK_FORWARD. Fail closed:

- dataset_id debe coincidir con el manifest;
- SHA-256 del manifest debe coincidir con el esperado (splits/v1.json);
- SHA-256 del CSV debe coincidir con la entrada del manifest;
- el rango nunca puede intersectar FINAL_HOLDOUT (guard `is_holdout_range`);
- timestamps estrictamente crecientes.

No muta datos, no resamplea, no genera datos sintéticos.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from domain.market.candle import Candle
from lab.splits import is_holdout_range

MANIFEST_REL = Path("docs/datasets/BYBIT_ETHBTC_V001.manifest.json")
SPLIT_V1_REL = Path("splits/v1.json")
CSV_DIR_REL = Path("datasets/BYBIT_ETHBTC_V001")


def sha256_file(path: Path) -> str:
    """Hex digest SHA-256 del contenido exacto del archivo."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class FrozenRange:
    """Descriptor inmutable del rango congelado servido por el adapter."""

    dataset_id: str
    symbol: str
    timeframe: str
    row_start: int
    row_end: int
    manifest_sha: str
    csv_sha: str


class FrozenDatasetAdapter:
    """Velas congeladas validadas para un rango de research permitido."""

    def __init__(
        self,
        *,
        dataset_id: str,
        symbol: str,
        timeframe: str,
        manifest_path: Path,
        csv_path: Path,
        expected_manifest_sha: str,
        row_start: int,
        row_end: int,
    ) -> None:
        if isinstance(row_start, bool) or isinstance(row_end, bool):
            raise ValueError("range bounds must be integers")
        if not isinstance(row_start, int) or not isinstance(row_end, int):
            raise ValueError("range bounds must be integers")
        if row_start < 0 or row_end <= row_start:
            raise ValueError(f"invalid range: [{row_start}, {row_end})")
        if not manifest_path.is_file():
            raise ValueError(f"manifest not found: {manifest_path}")
        manifest_sha = sha256_file(manifest_path)
        if manifest_sha != expected_manifest_sha:
            raise ValueError("manifest SHA mismatch: frozen dataset identity changed")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("dataset_version") != dataset_id:
            raise ValueError(f"dataset_id mismatch: {manifest.get('dataset_version')!r}")
        entry = self._find_entry(manifest, symbol=symbol, timeframe=timeframe)
        if not csv_path.is_file():
            raise ValueError(f"csv not found: {csv_path}")
        csv_sha = sha256_file(csv_path)
        if csv_sha != entry["sha256"]:
            raise ValueError("csv SHA mismatch: frozen dataset file changed")
        rows = self._read_rows(csv_path)
        if len(rows) != entry["row_count"]:
            raise ValueError("csv row count mismatch vs manifest")
        if row_end > len(rows):
            raise ValueError(f"range end {row_end} beyond dataset rows {len(rows)}")
        if is_holdout_range(row_start, row_end):
            raise ValueError("range intersects FINAL_HOLDOUT: access denied")
        candles = tuple(self._to_candle(row) for row in rows[row_start:row_end])
        self._check_order(candles)
        self._range = FrozenRange(
            dataset_id=dataset_id,
            symbol=str(entry["symbol"]),
            timeframe=str(entry["timeframe"]),
            row_start=row_start,
            row_end=row_end,
            manifest_sha=manifest_sha,
            csv_sha=csv_sha,
        )
        self._candles = candles

    @classmethod
    def from_repo(
        cls, repo_root: Path, *, symbol: str, timeframe: str, row_start: int, row_end: int
    ) -> FrozenDatasetAdapter:
        """Resuelve rutas oficiales + SHA esperado desde splits/v1.json."""
        split_v1 = json.loads((repo_root / SPLIT_V1_REL).read_text(encoding="utf-8"))
        manifest_path = repo_root / MANIFEST_REL
        csv_path = repo_root / CSV_DIR_REL / f"{symbol}_{timeframe}.csv"
        return cls(
            dataset_id=str(split_v1["dataset_id"]),
            symbol=symbol,
            timeframe=timeframe,
            manifest_path=manifest_path,
            csv_path=csv_path,
            expected_manifest_sha=str(split_v1["dataset_manifest_sha"]),
            row_start=row_start,
            row_end=row_end,
        )

    @staticmethod
    def _find_entry(manifest: dict[str, Any], *, symbol: str, timeframe: str) -> dict[str, Any]:
        files = manifest.get("files")
        if not isinstance(files, list):
            raise ValueError("manifest has no files section")
        for entry in files:
            if (
                isinstance(entry, dict)
                and entry.get("symbol") == symbol
                and entry.get("timeframe") == timeframe
            ):
                return entry
        raise ValueError(f"no manifest entry for {symbol} {timeframe}")

    @property
    def range(self) -> FrozenRange:
        return self._range

    @property
    def candles(self) -> tuple[Candle, ...]:
        """Velas originales en orden temporal (tupla inmutable, sin copia)."""
        return self._candles

    def __len__(self) -> int:
        return len(self._candles)

    def __iter__(self) -> Iterator[Candle]:
        return iter(self._candles)

    @staticmethod
    def _read_rows(csv_path: Path) -> list[dict[str, str]]:
        with open(csv_path, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _to_candle(row: dict[str, str]) -> Candle:
        return Candle(
            timestamp_ms=int(row["timestamp_ms"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            turnover=float(row["turnover"]),
        )

    @staticmethod
    def _check_order(candles: tuple[Candle, ...]) -> None:
        for prev, nxt in zip(candles, candles[1:], strict=False):
            if nxt.timestamp_ms <= prev.timestamp_ms:
                raise ValueError("timestamps out-of-order: frozen dataset corrupted")
