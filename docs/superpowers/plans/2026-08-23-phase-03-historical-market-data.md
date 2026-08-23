# Phase 03 — Historical Market Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development o superpowers:executing-plans. Steps usan checkbox (`- [ ]`).

**Goal:** Descargar ≥36 meses de candles spot ETHUSDT/BTCUSDT (15m/1h/4h) de Bybit, validarlas, persistirlas en CSV congelado + PostgreSQL, y generar manifest + SHA-256 reproducibles.

**Architecture:** Monolito hexagonal (PRD §8–9). `domain/market` (Candle, Timeframe, DatasetManifest puros), `application/ports` (Protocols: `MarketDataClient`, `DatasetStore`, `MarketCandleRepository`, `DatasetManifestRepository`), `application/services` (validación + orquestación de ingest), `infrastructure/bybit` (REST v5), `infrastructure/storage` (CSV + checksum + manifest file), `infrastructure/database` (ORM + repos). Dataset congelado en `datasets/` (gitignored); manifest en `docs/datasets/` (versionado).

**Tech Stack:** httpx (async), Pydantic v2 (schemas de respuesta), SQLAlchemy 2.x + Alembic, `csv`/`hashlib` stdlib. Sin pandas/pyarrow.

## Global Constraints

- Sin instalación sin DP-004 APPROVED (PRD §11). Único cambio de deps: `httpx` pasa de dev a runtime.
- Estructura hexagonal: `domain ← application ← interfaces`; `infrastructure` implementa puertos. Dominio puro = CERO frameworks (dataclasses, no Pydantic).
- Alembic obligatorio para TODO cambio de esquema; migración con `upgrade()` + `downgrade()` + test up→down→up (PRD §56).
- Dataset en `datasets/` FUERA de git; manifest (source, rango, symbols, timeframes, row counts, SHA-256, download command, schema version) SÍ en git (PRD §40).
- Idempotente: re-ejecutar ingest no duplica candles (upsert) ni cambia el checksum (determinista).
- Secrets SOLO en `.env` (el endpoint kline spot es público: sin API key).
- Coverage `--cov=src --cov-branch --cov-fail-under=90`; mypy strict; ruff.
- Grafo de codebase-memory a la par (AGENTS.md §4.13): re-index tras commit.
- Symbolos/timeframes fijos: `ETHUSDT`, `BTCUSDT` × `15m`, `1h`, `4h`. Categoría `spot`.

---

### Task 1: DP-004 + USER GATE

**Files:** Create `docs/phases/03/DP-004-httpx-runtime.md`

**Produces:** decisión APPROVED que autoriza mover `httpx` de dev a runtime (el adapter de Bybit lo importa en producción).

- [ ] **Step 1:** Escribir la proposal (runtime `httpx>=0.28.1`; ya instalado en dev; por qué no `aiohttp`/stdlib; rollback).
- [ ] **Step 2:** Presentar al usuario y esperar APPROVED.

---

### Task 2: Domain — Timeframe + Candle (TDD)

**Files:**
- Create: `src/domain/market/candle.py`
- Test: `tests/test_candle.py`

**Interfaces:**
- Produce `Timeframe(str, Enum)` con miembros `M15="15"`, `H1="60"`, `H4="240"`, propiedades `minutes -> int`, `label -> str` (`"15m"`, `"1h"`, `"4h"`), y `Timeframe.from_label(label: str) -> Timeframe` (raise `ValueError` si desconocido).
- Produce `Candle` (dataclass `frozen=True, slots=True`) con `timestamp_ms: int, open: float, high: float, low: float, close: float, volume: float, turnover: float`, propiedad `timestamp -> datetime` (UTC), e invariantes en `__post_init__`.

- [ ] **Step 1:** Escribir el test que falla

```python
import pytest
from datetime import UTC, datetime

from domain.market.candle import Candle, Timeframe


def test_timeframe_minutes_and_label() -> None:
    assert Timeframe.M15.minutes == 15
    assert Timeframe.M15.label == "15m"
    assert Timeframe.H1.minutes == 60
    assert Timeframe.H1.label == "1h"
    assert Timeframe.H4.minutes == 240
    assert Timeframe.H4.label == "4h"


def test_timeframe_from_label_roundtrip() -> None:
    assert Timeframe.from_label("15m") is Timeframe.M15
    assert Timeframe.from_label("1h") is Timeframe.H1
    assert Timeframe.from_label("4h") is Timeframe.H4


def test_timeframe_from_label_unknown_raises() -> None:
    with pytest.raises(ValueError):
        Timeframe.from_label("5m")


def test_candle_timestamp_utc() -> None:
    c = Candle(1_700_000_000_000, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)
    assert c.timestamp == datetime.fromtimestamp(1_700_000_000, tz=UTC)


@pytest.mark.parametrize(
    "fields",
    [
        (100.0, 90.0, 90.0, 100.0, 1.0, 100.0),   # high < max(open, close)
        (100.0, 110.0, 110.0, 100.0, 1.0, 100.0),  # low > min(open, close)
        (100.0, 110.0, 90.0, 100.0, -1.0, 100.0),  # volume negativo
        (100.0, 110.0, 90.0, 100.0, 1.0, -1.0),    # turnover negativo
    ],
)
def test_candle_invariants_raise(fields: tuple[float, ...]) -> None:
    o, h, l, c, v, t = fields
    with pytest.raises(ValueError):
        Candle(1_700_000_000_000, o, h, l, c, v, t)
```

- [ ] **Step 2:** Run test → FAIL (module not found).
- [ ] **Step 3:** Implementar `src/domain/market/candle.py`

```python
"""Entidades puras del dominio de mercado (PRD §13, §40). Sin frameworks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

_LABELS = {"15": "15m", "60": "1h", "240": "4h"}


class Timeframe(str, Enum):
    """Intervalo de vela; `value` es el intervalo Bybit REST v5 (minutos)."""

    M15 = "15"
    H1 = "60"
    H4 = "240"

    @property
    def minutes(self) -> int:
        return int(self.value)

    @property
    def label(self) -> str:
        return _LABELS[self.value]

    @classmethod
    def from_label(cls, label: str) -> "Timeframe":
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f"timeframe desconocido: {label}")


@dataclass(frozen=True, slots=True)
class Candle:
    """Vela OHLCV confirmada. `timestamp_ms` es el inicio del intervalo (epoch ms UTC)."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=UTC)

    def __post_init__(self) -> None:
        if self.high < max(self.open, self.close):
            raise ValueError("high < max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low > min(open, close)")
        if self.volume < 0:
            raise ValueError("volume negativo")
        if self.turnover < 0:
            raise ValueError("turnover negativo")
```

- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5:** Commit (con autorización): `feat(phase-03): dominio Candle + Timeframe`.

---

### Task 3: Domain — DatasetManifest (TDD)

**Files:**
- Create: `src/domain/market/dataset.py`
- Test: `tests/test_dataset.py`

**Interfaces:**
- Produce `CandleFileEntry` (dataclass frozen): `symbol: str, timeframe: str, path: str, row_count: int, sha256: str, start_ms: int, end_ms: int` con `to_dict()/from_dict()`.
- Produce `DatasetManifest` (dataclass frozen): `dataset_version: str, source: str, schema_version: str, symbols: tuple[str, ...], timeframes: tuple[str, ...], downloaded_at: str, download_command: str, files: tuple[CandleFileEntry, ...]` con `to_dict()/from_dict()` (roundtrip sin pérdida).

- [ ] **Step 1:** Escribir el test que falla

```python
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
```

- [ ] **Step 2:** Run test → FAIL.
- [ ] **Step 3:** Implementar `src/domain/market/dataset.py`

```python
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
    def from_dict(cls, data: dict[str, Any]) -> "CandleFileEntry":
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
    def from_dict(cls, data: dict[str, Any]) -> "DatasetManifest":
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
```

- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5:** Commit: `feat(phase-03): dominio DatasetManifest`.

---

### Task 4: Application — Puertos (Protocols)

**Files:**
- Create: `src/application/ports/market_data.py`
- Create: `src/application/ports/dataset_store.py`
- Create: `src/application/ports/market_repositories.py`

**Interfaces:**
- Produce `MarketDataClient` Protocol: `async def fetch_candles(self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int) -> list[Candle]` (ordenadas asc, dentro del rango).
- Produce `DatasetStore` Protocol (archivos): `write_candles(path, candles) -> int`, `read_candles(path) -> list[Candle]`, `compute_sha256(path) -> str`, `write_manifest(manifest, path) -> None`, `read_manifest(path) -> DatasetManifest`.
- Produce `MarketCandleRepository` Protocol: `upsert(symbol, timeframe, candles) -> int`, `count(symbol, timeframe) -> int`, `range(symbol, timeframe, start_ms, end_ms) -> list[Candle]`.
- Produce `DatasetManifestRepository` Protocol: `upsert(manifest) -> None`, `get(version) -> DatasetManifest | None`.

- [ ] **Step 1:** Escribir los cuatro Protocols (sin tests; son contratos tipados).

```python
# src/application/ports/market_data.py
from __future__ import annotations

from typing import Protocol

from domain.market.candle import Candle, Timeframe


class MarketDataClient(Protocol):
    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        """Candles ordenadas ascendente, dentro de [start_ms, end_ms] (inclusive)."""
        ...
```

```python
# src/application/ports/dataset_store.py
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
```

```python
# src/application/ports/market_repositories.py
from __future__ import annotations

from typing import Protocol

from domain.market.candle import Candle, Timeframe
from domain.market.dataset import DatasetManifest


class MarketCandleRepository(Protocol):
    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        """Inserta ignorando conflictos; devuelve filas insertadas."""
        ...

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        ...

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        """Candles con timestamp_ms en [start_ms, end_ms], ascendente."""
        ...


class DatasetManifestRepository(Protocol):
    async def upsert(self, manifest: DatasetManifest) -> None:
        ...

    async def get(self, version: str) -> DatasetManifest | None:
        ...
```

- [ ] **Step 2:** `ruff check` + `mypy src` verdes.
- [ ] **Step 3:** Commit: `feat(phase-03): puertos de market data y dataset`.

---

### Task 5: Application — Validación de dataset (TDD)

**Files:**
- Create: `src/application/services/validation.py`
- Test: `tests/test_validation.py`

**Interfaces:**
- Produce `ValidationResult` (dataclass frozen): `errors: tuple[str, ...]`, `warnings: tuple[str, ...]`.
- Produce `validate_candles(candles: list[Candle], timeframe: Timeframe) -> ValidationResult`:
  - **errors**: duplicados, fuera de orden, timestamp no alineado al intervalo.
  - **warnings**: huecos mayores al intervalo esperado (esperado = `timeframe.minutes * 60_000` ms).

- [ ] **Step 1:** Escribir el test que falla

```python
from application.services.validation import ValidationResult, validate_candles
from domain.market.candle import Candle, Timeframe

MS = 60_000


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)


def test_valid_continuous() -> None:
    r = validate_candles([mk(0), mk(15 * MS), mk(30 * MS)], Timeframe.M15)
    assert r.errors == ()
    assert r.warnings == ()


def test_duplicate_is_error() -> None:
    r = validate_candles([mk(0), mk(0), mk(15 * MS)], Timeframe.M15)
    assert any("duplicado" in e for e in r.errors)


def test_out_of_order_is_error() -> None:
    r = validate_candles([mk(15 * MS), mk(0)], Timeframe.M15)
    assert any("orden" in e for e in r.errors)


def test_misaligned_is_error() -> None:
    r = validate_candles([mk(1), mk(15 * MS)], Timeframe.M15)
    assert any("aline" in e for e in r.errors)


def test_gap_is_warning() -> None:
    r = validate_candles([mk(0), mk(45 * MS)], Timeframe.M15)
    assert r.errors == ()
    assert any("hueco" in w for w in r.warnings)


def test_empty_is_valid() -> None:
    r = validate_candles([], Timeframe.M15)
    assert r.errors == () and r.warnings == ()
```

- [ ] **Step 2:** Run test → FAIL.
- [ ] **Step 3:** Implementar `src/application/services/validation.py`

```python
"""Validación de calidad/completitud del dataset (PRD §40, data-pipeline-quality)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.market.candle import Candle, Timeframe


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_candles(candles: list[Candle], timeframe: Timeframe) -> ValidationResult:
    """Comprueba orden, unicidad, alineación y huecos. Nunca descarta filas."""
    errors: list[str] = []
    warnings: list[str] = []
    step_ms = timeframe.minutes * 60_000

    for i, c in enumerate(candles):
        if c.timestamp_ms % step_ms != 0:
            errors.append(f"timestamp no alineado en índice {i}: {c.timestamp_ms}")
        if i == 0:
            continue
        prev = candles[i - 1].timestamp_ms
        if c.timestamp_ms == prev:
            errors.append(f"timestamp duplicado: {c.timestamp_ms}")
        elif c.timestamp_ms < prev:
            errors.append(f"fuera de orden: {c.timestamp_ms} < {prev}")
        elif c.timestamp_ms - prev > step_ms:
            warnings.append(
                f"hueco entre {prev} y {c.timestamp_ms} "
                f"(esperado {step_ms} ms)"
            )

    return ValidationResult(tuple(errors), tuple(warnings))
```

- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5:** Commit: `feat(phase-03): validación de candles`.

---

### Task 6: Infraestructura — Bybit REST client (TDD)

**Files:**
- Create: `src/infrastructure/bybit/schemas.py`
- Create: `src/infrastructure/bybit/client.py`
- Create: `tests/fixtures/bybit_kline_spot.json`
- Test: `tests/test_bybit_client.py`

**Interfaces:**
- Produce `BybitRestClient` con `__init__(base_url: str = "https://api.bybit.com", timeout: float = 10.0, transport: httpx.AsyncBaseTransport | None = None, max_retries: int = 3)`, `async close()`, `async fetch_candles(symbol, interval, start_ms, end_ms) -> list[Candle]`.
- Produce `BybitError(Exception)`.
- Paginación: iterar hacia atrás con `end` decreciente (límite 1000 por request); retries en 429/5xx con backoff; `retCode != 0` → `BybitError`.

- [ ] **Step 1:** Grabar el fixture real (un único request, respuesta capturada 2026-08-23)

```bash
curl -s "https://api.bybit.com/v5/market/kline?category=spot&symbol=ETHUSDT&interval=15&limit=3" \
  -o tests/fixtures/bybit_kline_spot.json
```

- [ ] **Step 2:** Escribir el test que falla (usa `httpx.MockTransport`)

```python
import json
from pathlib import Path

import httpx
import pytest

from domain.market.candle import Timeframe
from infrastructure.bybit.client import BybitError, BybitRestClient

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "bybit_kline_spot.json").read_text()
)


@pytest.fixture
def client() -> BybitRestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v5/market/kline"
        return httpx.Response(200, json=FIXTURE)

    return BybitRestClient(transport=httpx.MockTransport(handler))


async def test_fetch_parses_candles(client: BybitRestClient) -> None:
    candles = await client.fetch_candles("ETHUSDT", Timeframe.M15, 0, 2**62)
    assert len(candles) == len(FIXTURE["result"]["list"])
    assert candles == sorted(candles, key=lambda c: c.timestamp_ms)
    first = candles[0]
    assert first.high >= max(first.open, first.close)


async def test_retcode_nonzero_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "boom"})

    c = BybitRestClient(transport=httpx.MockTransport(handler))
    with pytest.raises(BybitError):
        await c.fetch_candles("ETHUSDT", Timeframe.M15, 0, 1)
    await c.close()


async def test_429_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=FIXTURE)

    c = BybitRestClient(transport=httpx.MockTransport(handler), max_retries=2)
    candles = await c.fetch_candles("ETHUSDT", Timeframe.M15, 0, 2**62)
    assert candles
    assert calls["n"] == 2
    await c.close()
```

- [ ] **Step 3:** Implementar `src/infrastructure/bybit/schemas.py`

```python
"""Esquemas de validación de respuestas Bybit REST v5 (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel


class KlineResult(BaseModel):
    category: str
    symbol: str
    list: list[list[str]]


class KlineResponse(BaseModel):
    retCode: int
    retMsg: str
    result: KlineResult
    time: int
```

- [ ] **Step 4:** Implementar `src/infrastructure/bybit/client.py`

```python
"""Adaptador REST histórico de Bybit (PRD §13, §40; skill bybit-integration)."""

from __future__ import annotations

import asyncio
import random

import httpx

from domain.market.candle import Candle, Timeframe
from infrastructure.bybit.schemas import KlineResponse

BASE_URL = "https://api.bybit.com"
KLINE_PATH = "/v5/market/kline"
MAX_LIMIT = 1000


class BybitError(Exception):
    """Error devuelto por la API de Bybit."""


def _parse_candle(row: list[str]) -> Candle:
    ts, o, h, l, c, v, t = row
    return Candle(
        timestamp_ms=int(ts),
        open=float(o),
        high=float(h),
        low=float(l),
        close=float(c),
        volume=float(v),
        turnover=float(t),
    )


class BybitRestClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=timeout, transport=transport
        )
        self._max_retries = max_retries

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_candles(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        candles: dict[int, Candle] = {}
        cursor = end_ms
        for _ in range(10_000):
            data = await self._get_kline(symbol, interval, start_ms, cursor)
            batch = [c for c in (_parse_candle(r) for r in data.result.list)]
            if not batch:
                break
            earliest = batch[0].timestamp_ms
            for c in batch:
                if start_ms <= c.timestamp_ms <= end_ms:
                    candles[c.timestamp_ms] = c
            if earliest <= start_ms:
                break
            cursor = earliest - 1
        return sorted(candles.values(), key=lambda c: c.timestamp_ms)

    async def _get_kline(
        self, symbol: str, interval: Timeframe, start_ms: int, end_ms: int
    ) -> KlineResponse:
        params = {
            "category": "spot",
            "symbol": symbol,
            "interval": interval.value,
            "start": start_ms,
            "end": end_ms,
            "limit": MAX_LIMIT,
        }
        for attempt in range(self._max_retries + 1):
            response = await self._client.get(KLINE_PATH, params=params)
            if response.status_code in (429,) or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                delay += random.uniform(0, 0.5)
                if attempt < self._max_retries:
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
            response.raise_for_status()
            payload = KlineResponse.model_validate(response.json())
            if payload.retCode != 0:
                raise BybitError(f"Bybit retCode={payload.retCode}: {payload.retMsg}")
            return payload
        raise BybitError("agotados los reintentos")
```

- [ ] **Step 5:** Run test → PASS.
- [ ] **Step 6:** `ruff check` + `mypy src` verdes.
- [ ] **Step 7:** Commit: `feat(phase-03): adapter REST histórico Bybit`.

---

### Task 7: Infraestructura — DatasetStore (CSV + SHA-256 + manifest) (TDD)

**Files:**
- Create: `src/infrastructure/storage/dataset_store.py`
- Test: `tests/test_dataset_store.py`

**Interfaces:**
- Produce `LocalDatasetStore` con los 5 métodos del Protocol `DatasetStore`. CSV header `timestamp_ms,open,high,low,close,volume,turnover`; roundtrip exacto; manifest JSON con `indent=2, sort_keys`.

- [ ] **Step 1:** Escribir el test que falla

```python
from pathlib import Path

from domain.market.candle import Candle, Timeframe
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
        dataset_version="V001", source="s", schema_version="1.0",
        symbols=("ETHUSDT",), timeframes=("15m",),
        downloaded_at="d", download_command="c",
        files=(CandleFileEntry("ETHUSDT", "15m", "p", 1, "abc", 0, 0),),
    )
    path = tmp_path / "manifest.json"
    STORE.write_manifest(m, path)
    assert STORE.read_manifest(path) == m
```

- [ ] **Step 2:** Run test → FAIL.
- [ ] **Step 3:** Implementar `src/infrastructure/storage/dataset_store.py`

```python
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
```

- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5:** Commit: `feat(phase-03): dataset store CSV + checksum + manifest`.

---

### Task 8: Infraestructura — ORM + migración 0002 (TDD/integración)

**Files:**
- Modify: `src/infrastructure/database/models.py`
- Create: `migrations/versions/0002_market_data.py`
- Test: `tests/test_models.py` (ampliar), `tests/integration/test_market_repository.py`

**Interfaces:**
- Produce ORM `MarketCandle` (tabla `market_candles`, unique `(symbol, timeframe, timestamp_ms)`, index homónimo).
- Produce ORM `DatasetManifestRecord` (tabla `dataset_manifests`, PK `dataset_version`).

- [ ] **Step 1:** Ampliar el test de modelos

```python
def test_market_candle_tabla() -> None:
    from infrastructure.database.models import MarketCandle

    assert MarketCandle.__tablename__ == "market_candles"


def test_dataset_manifest_record_tabla() -> None:
    from infrastructure.database.models import DatasetManifestRecord

    assert DatasetManifestRecord.__tablename__ == "dataset_manifests"
```

- [ ] **Step 2:** Implementar los modelos en `src/infrastructure/database/models.py`

```python
from sqlalchemy import BigInteger, DateTime, Float, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

class MarketCandle(Base):
    """Vela OHLCV persistida (PRD §55 market_candles)."""

    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    turnover: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp_ms", name="uq_market_candles_symbol_tf_ts"),
        Index("ix_market_candles_symbol_tf_ts", "symbol", "timeframe", "timestamp_ms"),
    )


class DatasetManifestRecord(Base):
    """Registro de manifest del dataset congelado (PRD §55 dataset_manifests)."""

    __tablename__ = "dataset_manifests"

    dataset_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    download_command: Mapped[str] = mapped_column(Text, nullable=False)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```

- [ ] **Step 3:** Crear la migración `migrations/versions/0002_market_data.py`

```python
"""market data: market_candles + dataset_manifests

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_candles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("turnover", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timeframe", "timestamp_ms", name="uq_market_candles_symbol_tf_ts"),
    )
    op.create_index(
        "ix_market_candles_symbol_tf_ts",
        "market_candles",
        ["symbol", "timeframe", "timestamp_ms"],
    )
    op.create_table(
        "dataset_manifests",
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("symbols", postgresql.JSONB(), nullable=False),
        sa.Column("timeframes", postgresql.JSONB(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_command", sa.Text(), nullable=False),
        sa.Column("files", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_version"),
    )


def downgrade() -> None:
    op.drop_table("dataset_manifests")
    op.drop_index("ix_market_candles_symbol_tf_ts", table_name="market_candles")
    op.drop_table("market_candles")
```

- [ ] **Step 4:** Escribir el test de integración de migración (ya existe `test_alembic.py` con roundtrip up→down→up; verificar que sigue verde con 0002).
- [ ] **Step 5:** `alembic upgrade head` contra la DB de test vía test suite; `ruff` + `mypy`.
- [ ] **Step 6:** Commit: `feat(phase-03): entidades market_candles + dataset_manifests (migración 0002)`.

---

### Task 9: Infraestructura — Repositorios SQLAlchemy (integración, TDD)

**Files:**
- Modify: `src/infrastructure/database/repositories.py`
- Test: `tests/integration/test_market_repository.py`

**Interfaces:**
- Produce `SqlAlchemyMarketCandleRepository(session)` con `upsert` (ON CONFLICT DO NOTHING + RETURNING), `count`, `range`.
- Produce `SqlAlchemyDatasetManifestRepository(session)` con `upsert`/`get`.

- [ ] **Step 1:** Escribir el test que falla

```python
from domain.market.candle import Candle, Timeframe
from domain.market.dataset import CandleFileEntry, DatasetManifest
from infrastructure.database.repositories import (
    SqlAlchemyDatasetManifestRepository,
    SqlAlchemyMarketCandleRepository,
)


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)


async def test_upsert_and_count(session) -> None:
    repo = SqlAlchemyMarketCandleRepository(session)
    inserted = await repo.upsert("ETHUSDT", Timeframe.M15, [mk(0), mk(15 * 60_000)])
    await session.commit()
    assert inserted == 2
    assert await repo.count("ETHUSDT", Timeframe.M15) == 2
    # re-upsert idempotente
    inserted_again = await repo.upsert("ETHUSDT", Timeframe.M15, [mk(0)])
    await session.commit()
    assert inserted_again == 0
    assert await repo.count("ETHUSDT", Timeframe.M15) == 2


async def test_range(session) -> None:
    repo = SqlAlchemyMarketCandleRepository(session)
    await repo.upsert("ETHUSDT", Timeframe.M15, [mk(0), mk(15 * 60_000), mk(30 * 60_000)])
    await session.commit()
    rows = await repo.range("ETHUSDT", Timeframe.M15, 15 * 60_000, 30 * 60_000)
    assert [c.timestamp_ms for c in rows] == [15 * 60_000, 30 * 60_000]


async def test_manifest_upsert_get(session) -> None:
    repo = SqlAlchemyDatasetManifestRepository(session)
    m = DatasetManifest(
        dataset_version="V001", source="s", schema_version="1.0",
        symbols=("ETHUSDT",), timeframes=("15m",),
        downloaded_at="d", download_command="c",
        files=(CandleFileEntry("ETHUSDT", "15m", "p", 1, "abc", 0, 0),),
    )
    await repo.upsert(m)
    await session.commit()
    assert await repo.get("V001") == m
    assert await repo.get("missing") is None
```

- [ ] **Step 2:** Run test → FAIL (falta `session` fixture en ese módulo: añadir `from sqlalchemy.ext.asyncio import AsyncSession` no es necesario; el fixture `session` ya vive en `tests/conftest.py`).
- [ ] **Step 3:** Implementar los repos en `src/infrastructure/database/repositories.py`

```python
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from domain.market.candle import Candle, Timeframe
from domain.market.dataset import DatasetManifest
from infrastructure.database.models import DatasetManifestRecord, MarketCandle


class SqlAlchemyMarketCandleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        if not candles:
            return 0
        rows = [
            {
                "symbol": symbol,
                "timeframe": timeframe.label,
                "timestamp_ms": c.timestamp_ms,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "turnover": c.turnover,
            }
            for c in candles
        ]
        stmt = (
            pg_insert(MarketCandle)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["symbol", "timeframe", "timestamp_ms"])
            .returning(MarketCandle.id)
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        stmt = (
            select(func.count())
            .select_from(MarketCandle)
            .where(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe.label)
        )
        return int(await self._session.scalar(stmt) or 0)

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        stmt = (
            select(MarketCandle)
            .where(
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == timeframe.label,
                MarketCandle.timestamp_ms >= start_ms,
                MarketCandle.timestamp_ms <= end_ms,
            )
            .order_by(MarketCandle.timestamp_ms)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [self._to_domain(r) for r in rows]

    @staticmethod
    def _to_domain(row: MarketCandle) -> Candle:
        return Candle(row.timestamp_ms, row.open, row.high, row.low, row.close, row.volume, row.turnover)


class SqlAlchemyDatasetManifestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, manifest: DatasetManifest) -> None:
        row = await self._session.get(DatasetManifestRecord, manifest.dataset_version)
        if row is None:
            row = DatasetManifestRecord(dataset_version=manifest.dataset_version)
            self._session.add(row)
        row.source = manifest.source
        row.schema_version = manifest.schema_version
        row.symbols = list(manifest.symbols)
        row.timeframes = list(manifest.timeframes)
        row.downloaded_at = datetime.fromisoformat(manifest.downloaded_at)
        row.download_command = manifest.download_command
        row.files = [f.to_dict() for f in manifest.files]
        await self._session.flush()

    async def get(self, version: str) -> DatasetManifest | None:
        row = await self._session.get(DatasetManifestRecord, version)
        if row is None:
            return None
        return DatasetManifest(
            dataset_version=row.dataset_version,
            source=row.source,
            schema_version=row.schema_version,
            symbols=tuple(row.symbols),
            timeframes=tuple(row.timeframes),
            downloaded_at=row.downloaded_at.isoformat(),
            download_command=row.download_command,
            files=tuple(CandleFileEntry.from_dict(f) for f in row.files),
        )
```

- [ ] **Step 4:** Run test → PASS (la DB de test ya se migra con up→down→up en `conftest.py`).
- [ ] **Step 5:** Commit: `feat(phase-03): repositorios SQLAlchemy de market data`.

---

### Task 10: Application — HistoricalDataService (orquestación, TDD)

**Files:**
- Create: `src/application/services/historical_data.py`
- Test: `tests/test_historical_service.py`

**Interfaces:**
- Produce `IngestRequest` (dataclass): `dataset_version, symbols: tuple[str,...], timeframes: tuple[Timeframe,...], start_ms: int, end_ms: int, data_dir: Path, manifest_path: Path, download_command: str`.
- Produce `IngestFileResult` (dataclass frozen): `symbol, timeframe, path, row_count, sha256, start_ms, end_ms, warnings: tuple[str,...]`.
- Produce `IngestReport` (dataclass frozen): `dataset_version, files: tuple[IngestFileResult,...], manifest: DatasetManifest`.
- Produce `HistoricalDataService(client, store, candle_repo, manifest_repo)` con `async ingest(request) -> IngestReport`. Flujo por (symbol, timeframe): fetch → validate (aborta con `ValueError` si `errors`) → write CSV → sha256 → upsert DB → entry. Luego manifiesto (archivo + DB).

- [ ] **Step 1:** Escribir el test que falla (fakes en memoria)

```python
from pathlib import Path

import pytest

from application.services.historical_data import (
    HistoricalDataService,
    IngestRequest,
)
from domain.market.candle import Candle, Timeframe
from domain.market.dataset import CandleFileEntry, DatasetManifest


class FakeClient:
    def __init__(self, candles: dict[tuple[str, Timeframe], list[Candle]]) -> None:
        self._candles = candles

    async def fetch_candles(self, symbol, interval, start_ms, end_ms):
        return self._candles[(symbol, interval)]


class FakeStore:
    def __init__(self) -> None:
        self.manifests: list[tuple[DatasetManifest, Path]] = []

    def write_candles(self, path, candles):
        return len(candles)

    def read_candles(self, path):
        return []

    def compute_sha256(self, path):
        return "a" * 64

    def write_manifest(self, manifest, path):
        self.manifests.append((manifest, path))

    def read_manifest(self, path):
        raise NotImplementedError


class FakeCandleRepo:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, Timeframe, int]] = []

    async def upsert(self, symbol, timeframe, candles):
        self.upserts.append((symbol, timeframe, len(candles)))
        return len(candles)

    async def count(self, symbol, timeframe):
        return 0

    async def range(self, symbol, timeframe, start_ms, end_ms):
        return []


class FakeManifestRepo:
    def __init__(self) -> None:
        self.saved: list[DatasetManifest] = []

    async def upsert(self, manifest):
        self.saved.append(manifest)

    async def get(self, version):
        return None


def mk(ts: int) -> Candle:
    return Candle(ts, 100.0, 110.0, 90.0, 105.0, 1.0, 100.0)


def make_service():
    return HistoricalDataService(
        client=FakeClient({("ETHUSDT", Timeframe.M15): [mk(0), mk(15 * 60_000)]}),
        store=FakeStore(),
        candle_repo=FakeCandleRepo(),
        manifest_repo=FakeManifestRepo(),
    )


async def test_ingest_happy_path(tmp_path: Path) -> None:
    svc = make_service()
    req = IngestRequest(
        dataset_version="V001", symbols=("ETHUSDT",), timeframes=(Timeframe.M15,),
        start_ms=0, end_ms=15 * 60_000, data_dir=tmp_path,
        manifest_path=tmp_path / "manifest.json", download_command="cmd",
    )
    report = await svc.ingest(req)
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
        store=FakeStore(), candle_repo=FakeCandleRepo(), manifest_repo=FakeManifestRepo(),
    )
    req = IngestRequest(
        dataset_version="V001", symbols=("ETHUSDT",), timeframes=(Timeframe.M15,),
        start_ms=0, end_ms=30 * 60_000, data_dir=tmp_path,
        manifest_path=tmp_path / "manifest.json", download_command="cmd",
    )
    with pytest.raises(ValueError):
        await svc.ingest(req)
```

- [ ] **Step 2:** Run test → FAIL.
- [ ] **Step 3:** Implementar `src/application/services/historical_data.py`

```python
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
from domain.market.candle import Candle, Timeframe
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

                rel_path = f"{request.data_dir.name}/{symbol}_{timeframe.label}.csv"
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
```

- [ ] **Step 4:** Run test → PASS.
- [ ] **Step 5:** Commit: `feat(phase-03): servicio de ingesta histórica`.

---

### Task 11: Interfaces — CLI download + verify (TDD)

**Files:**
- Create: `src/interfaces/cli/download.py`
- Modify: `src/main.py`
- Modify: `src/settings.py`, `config/base.yaml`
- Test: `tests/test_main.py` (ampliar)

**Interfaces:**
- Produce `build_historical_data_service(settings)` que compone BybitRestClient + LocalDatasetStore + repos SQLAlchemy.
- Produce `download(argv) -> int` y `verify(argv) -> int`.
- `main.py` gana subcomandos `download` y `verify`; sin argumentos mantiene el comportamiento actual (imprime versión).

- [ ] **Step 1:** Añadir settings (`bybit_base_url`, `bybit_request_timeout`, `dataset_dir`)

```python
# src/settings.py
    bybit_base_url: str = "https://api.bybit.com"
    bybit_request_timeout: float = 10.0
    dataset_dir: str = "datasets"
```

```yaml
# config/base.yaml (añadir)
bybit_base_url: https://api.bybit.com
bybit_request_timeout: 10.0
dataset_dir: datasets
```

- [ ] **Step 2:** Escribir el test del CLI

```python
def test_download_help_lists_subcommands() -> None:
    from main import main

    assert main(["download", "--help"]) == 0


def test_verify_help() -> None:
    from main import main

    assert main(["verify", "--help"]) == 0
```

- [ ] **Step 3:** Implementar `src/interfaces/cli/download.py` y cablear `src/main.py`

```python
# src/interfaces/cli/download.py
"""Subcomandos de ingesta y verificación del dataset histórico."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from application.ports.dataset_store import DatasetStore
from application.ports.market_repositories import (
    DatasetManifestRepository,
    MarketCandleRepository,
)
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
    now = datetime.now(UTC)
    start = now - timedelta(days=30 * months)
    return int(start.timestamp() * 1000)


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _parse_timeframes(labels: list[str]) -> tuple[Timeframe, ...]:
    return tuple(Timeframe.from_label(l) for l in labels)


def _build_service(settings: Settings):
    from sqlalchemy.ext.asyncio import AsyncSession

    engine = create_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    session = session_factory()

    client = BybitRestClient(
        base_url=settings.bybit_base_url, timeout=settings.bybit_request_timeout
    )
    store = LocalDatasetStore()
    candle_repo = SqlAlchemyMarketCandleRepository(session)
    manifest_repo = SqlAlchemyDatasetManifestRepository(session)
    return HistoricalDataService(client, store, candle_repo, manifest_repo), client, engine, session


async def _download(settings: Settings, args: argparse.Namespace) -> int:
    service, client, engine, session = _build_service(settings)
    try:
        timeframes = _parse_timeframes(args.timeframes)
        start_ms = args.start_ms if args.start_ms is not None else _months_ago_ms(args.months)
        end_ms = args.end_ms if args.end_ms is not None else _now_ms()
        data_dir = Path(settings.dataset_dir) / args.dataset_version
        manifest_path = Path("docs") / "datasets" / f"{args.dataset_version}.manifest.json"
        request = IngestRequest(
            dataset_version=args.dataset_version,
            symbols=tuple(args.symbols),
            timeframes=timeframes,
            start_ms=start_ms,
            end_ms=end_ms,
            data_dir=data_dir,
            manifest_path=manifest_path,
            download_command=" ".join(["python", "-m", "main", "download"] + sys.argv[1:]),
        )
        report = await service.ingest(request)
        await session.commit()
        print(json.dumps(
            {
                "dataset_version": report.dataset_version,
                "files": [
                    {"symbol": f.symbol, "timeframe": f.timeframe.label,
                     "rows": f.row_count, "sha256": f.sha256, "warnings": list(f.warnings)}
                    for f in report.files
                ],
            },
            indent=2,
        ))
        return 0
    finally:
        await session.close()
        await engine.dispose()
        await client.close()


async def _verify(settings: Settings, args: argparse.Namespace) -> int:
    store = LocalDatasetStore()
    manifest_path = Path("docs") / "datasets" / f"{args.dataset_version}.manifest.json"
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
    settings = Settings()
    parser = argparse.ArgumentParser(prog="download")
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    parser.add_argument("--symbols", nargs="+", default=["ETHUSDT", "BTCUSDT"])
    parser.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h"])
    parser.add_argument("--months", type=int, default=36)
    parser.add_argument("--start-ms", type=int, default=None)
    parser.add_argument("--end-ms", type=int, default=None)
    args = parser.parse_args(argv)
    return asyncio.run(_download(settings, args))


def verify(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="verify")
    parser.add_argument("--dataset-version", default=DEFAULT_DATASET)
    args = parser.parse_args(argv)
    return asyncio.run(_verify(Settings(), args))
```

```python
# src/main.py (ampliar)
def main(argv: list[str] | None = None) -> int:
    import argparse

    from interfaces.cli import download as cli

    parser = argparse.ArgumentParser(prog="self-evaluating-trading-agent")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("download")
    sub.add_parser("verify")
    args, rest = parser.parse_known_args(argv)
    if args.command == "download":
        return cli.download(rest)
    if args.command == "verify":
        return cli.verify(rest)
    print(f"self-evaluating-trading-agent {__version__}")
    return 0
```

- [ ] **Step 4:** Run test → PASS. `ruff` + `mypy src`.
- [ ] **Step 5:** Commit: `feat(phase-03): CLI download/verify`.

---

### Task 12: Ejecución real + dataset congelado + evidencias + gate

**Files:** evidencia en `docs/phases/03/evidence/`, manifest versionado `docs/datasets/BYBIT_ETHBTC_V001.manifest.json`.

- [ ] **Step 1:** Descarga real: `uv run python -m main download --dataset-version BYBIT_ETHBTC_V001` (36 meses × 2 symbols × 3 timeframes), registrando con `evidence.sh 03 download -- ...`.
- [ ] **Step 2:** Verificación: `uv run python -m main verify --dataset-version BYBIT_ETHBTC_V001` (reload + SHA-256).
- [ ] **Step 3:** `uv run pytest --cov=src --cov-branch --cov-fail-under=90` → `docs/phases/03/evidence/coverage.json`.
- [ ] **Step 4:** `uv run ruff check . && uv run ruff format --check .` → `lint.log`; `uv run mypy src tests` → `typing.log`.
- [ ] **Step 5:** `python3 harness/scripts/gate_check.py --phase 03` (0 FAIL).
- [ ] **Step 6:** `python3 harness/scripts/progress.py mark-done` por cada entregable con su evidencia.
- [ ] **Step 7:** `gen_report.py --phase 03`, completar las 30 secciones, UAT instructivo.
- [ ] **Step 8:** Presentar UAT + gate-request al usuario.

---

## Self-Review

- **Spec coverage:** PRD §13 (ETHUSDT/BTCUSDT, 15m/1h/4h, spot) → Tasks 2,6,11; §40 (36 meses, datasets/ fuera de git, manifest con source/range/symbols/timeframes/rows/SHA-256/command/schema) → Tasks 3,7,10,11,12; §41 (dataset_version BYBIT_ETHBTC_V001, hash verificado) → Tasks 3,11,12; §55 (market_candles, dataset_manifests) → Task 8; §56 (migración+up/down test) → Task 8; E2E download→validate→persist→checksum→reload → Tasks 10,12.
- **Type consistency:** `Timeframe` (enum con `.label`, `.value`, `.minutes`, `from_label`) usado consistentemente en ports, service y repos; `Candle` (frozen, 7 campos) idéntico en domain, bybit parser, store y repo; `DatasetManifest`/`CandleFileEntry` con `to_dict/from_dict` compartidos por store, repo y service.
- **Placeholder scan:** sin TBD/TODO; cada tarea lleva código completo.

## Execution Handoff

Plan guardado en `docs/superpowers/plans/2026-08-23-phase-03-historical-market-data.md`.
