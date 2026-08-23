"""Puerto de persistencia del dataset congelado en archivos (Protocol)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from domain.market.candle import Candle
from domain.market.dataset import DatasetManifest


class DatasetStore(Protocol):
    def write_candles(self, path: Path, candles: list[Candle]) -> int:
        """Escribe CSV y devuelve el número de filas escritas."""
        ...

    def read_candles(self, path: Path) -> list[Candle]:
        """Lee el CSV y reconstruye las velas en orden ascendente."""
        ...

    def compute_sha256(self, path: Path) -> str:
        """Hex digest SHA-256 del contenido del archivo."""
        ...

    def write_manifest(self, manifest: DatasetManifest, path: Path) -> None:
        """Serializa el manifest a JSON."""
        ...

    def read_manifest(self, path: Path) -> DatasetManifest:
        """Lee y valida un manifest JSON."""
        ...
