"""Bronze idempotente de trades históricos Spot de Bybit.

Fuente canónica: ``https://public.bybit.com/spot/<SYMBOL>/<SYMBOL>_YYYY-MM-DD.csv.gz``
(archivos diarios). NUNCA ``/trading/`` — el guard de base lo rechaza.

Invariantes (skill medallion-market-data + ADR-0005/0007):

- El ``.csv.gz`` se conserva byte-for-byte (gzip original intacto).
- Descarga a ``<archivo>.csv.gz.part`` → validación gzip (CRC) → SHA-256 →
  manifiesto (atómico) → ``os.replace`` atómico al destino final.
- Archivo ya presente + hash igual al manifiesto ⇒ SKIP sin red.
- Archivo ya presente + hash distinto (o sin manifiesto) ⇒ FAIL CLOSED.
- Split guard ANTES de la red: solo días completos de DEVELOPMENT.
- Salidas deterministas: ``manifest.json`` sin timestamps (claves ordenadas);
  los tiempos operativos van a ``ops-downloads.jsonl`` (separado).
- El schema de la fuente se detecta del header REAL de cada archivo
  (V1 = 5 columnas, V2 = 6 columnas con ``rpi`` final): cualquier otro header
  u orden ⇒ FAIL CLOSED. El campo ``schema_version`` de cada entrada registra
  esa versión detectada; el ``schema_version`` del manifiesto sigue siendo el
  de compatibilidad del propio manifiesto.

Solo stdlib: ejecutable en el Python del sistema (lenovosrv) sin venv.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from infrastructure.medallion.split_guard import (
    DEFAULT_INGEST_SCOPE,
    IngestScope,
    SplitGuardError,
    ensure_development_day,
    ensure_ingest_allowed,
)

__all__ = [
    "BRONZE_HEADER_V1",
    "BRONZE_HEADER_V2",
    "BRONZE_SCHEMA_VERSION",
    "DEFAULT_BASE_URL",
    "BronzeError",
    "DownloadResult",
    "HashConflictError",
    "InvalidGzipError",
    "MarkerError",
    "SchemaBackfillResult",
    "SOURCE_HEADERS",
    "SOURCE_SCHEMA_V1",
    "SOURCE_SCHEMA_V2",
    "SplitGuardError",
    "SourceSchemaError",
    "UnexpectedFilenameError",
    "backfill_source_schema",
    "bronze_filename",
    "detect_source_schema",
    "download_day",
    "download_days",
    "ensure_marker",
    "load_manifest",
    "read_source_schema",
    "sha256_file",
    "source_url",
    "urllib_fetch",
    "validate_gzip_file",
]

BRONZE_SCHEMA_VERSION = "bybit-spot-trades-csv-gz-v1"
SOURCE_SCHEMA_V1 = "bybit-spot-trades-csv-gz-v1"
SOURCE_SCHEMA_V2 = "bybit-spot-trades-csv-gz-v2"
BRONZE_HEADER_V1 = ("id", "timestamp", "price", "volume", "side")
BRONZE_HEADER_V2 = ("id", "timestamp", "price", "volume", "side", "rpi")
SOURCE_HEADERS: dict[str, tuple[str, ...]] = {
    SOURCE_SCHEMA_V1: BRONZE_HEADER_V1,
    SOURCE_SCHEMA_V2: BRONZE_HEADER_V2,
}
DEFAULT_BASE_URL = "https://public.bybit.com/spot"
MARKER_EXPECTED_FIRST_LINE = "LENOVO_DATA"
GZIP_MAGIC = b"\x1f\x8b"
_FILENAME_RE = re.compile(r"^[A-Z0-9]{2,20}_\d{4}-\d{2}-\d{2}\.csv\.gz$")
_CHUNK = 1 << 20


class BronzeError(RuntimeError):
    """Error base de la capa Bronze (fail closed)."""


class UnexpectedFilenameError(BronzeError):
    """Nombre de archivo inesperado o con path traversal."""


class InvalidGzipError(BronzeError):
    """El payload descargado no es un gzip válido (magic/CRC)."""


class HashConflictError(BronzeError):
    """El archivo presente no coincide con el manifiesto: jamás sobrescribir."""


class MarkerError(BronzeError):
    """Marker de volumen ausente o inválido en /srv/data."""


class SourceSchemaError(BronzeError):
    """Header de la fuente desconocido, reordenado o ilegible (fail closed)."""


Fetcher = Callable[[str, Path], int]


@dataclass(frozen=True)
class DownloadResult:
    filename: str
    status: str  # "downloaded" | "skipped"
    sha256: str
    bytes: int


def bronze_filename(symbol: str, day: date) -> str:
    if not re.fullmatch(r"[A-Z0-9]{2,20}", symbol):
        raise UnexpectedFilenameError(f"symbol inválido: {symbol!r}")
    return f"{symbol}_{day.isoformat()}.csv.gz"


def validate_filename(name: str, symbol: str, day: date) -> None:
    """Rechaza path traversal y cualquier nombre distinto del esperado."""
    if not _FILENAME_RE.fullmatch(name) or "/" in name or "\\" in name or ".." in name:
        raise UnexpectedFilenameError(f"nombre de archivo inesperado: {name!r}")
    if name != bronze_filename(symbol, day):
        raise UnexpectedFilenameError(
            f"nombre {name!r} != esperado {bronze_filename(symbol, day)!r}"
        )


def source_url(base_url: str, symbol: str, day: date) -> str:
    """Construye la URL diaria; prohíbe bases fuera del datacenter público Spot."""
    base = base_url.rstrip("/")
    allowed_prefix = "https://public.bybit.com/spot"
    if not base.startswith(allowed_prefix) or "/trading" in base:
        raise BronzeError(f"base URL no permitida: {base_url!r}")
    name = bronze_filename(symbol, day)
    validate_filename(name, symbol, day)
    return f"{base}/{symbol}/{name}"


def urllib_fetch(url: str, dest: Path) -> int:
    """Descarga ``url`` a ``dest`` con stdlib (streaming por chunks)."""
    request = Request(url, headers={"User-Agent": "seta-medallion-bronze/1"})
    written = 0
    with urlopen(request, timeout=120) as response, dest.open("wb") as fh:
        while chunk := response.read(_CHUNK):
            fh.write(chunk)
            written += len(chunk)
    return written


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def validate_gzip_file(path: Path) -> None:
    """Valida magic bytes y CRC leyendo el stream completo (falla cerrado)."""
    with path.open("rb") as fh:
        if fh.read(2) != GZIP_MAGIC:
            raise InvalidGzipError(f"magic gzip ausente en {path.name}")
    try:
        with gzip.open(path, "rb") as gz:
            while gz.read(_CHUNK):
                pass
    except (EOFError, OSError) as exc:
        raise InvalidGzipError(f"gzip corrupto en {path.name}: {exc}") from exc


def detect_source_schema(header: Sequence[str]) -> str:
    """Devuelve la versión de schema de la fuente a partir del header real.

    FAIL CLOSED: cualquier header desconocido o con las columnas reordenadas
    levanta ``SourceSchemaError`` (jamás se asumen columnas fijas).
    """
    known = tuple(header)
    for version, expected in SOURCE_HEADERS.items():
        if known == expected:
            return version
    allowed = [list(columns) for columns in SOURCE_HEADERS.values()]
    raise SourceSchemaError(
        f"header de fuente desconocido u orden alterado: {list(known)!r} (esperado {allowed})"
    )


def read_source_schema(path: Path) -> str:
    """Lee la cabecera del ``.csv.gz`` y devuelve su schema de fuente."""
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            try:
                header = tuple(next(reader))
            except StopIteration as exc:
                raise SourceSchemaError(f"archivo vacío: {path.name}") from exc
    except SourceSchemaError:
        raise
    except (OSError, EOFError, UnicodeDecodeError, csv.Error) as exc:
        raise SourceSchemaError(f"cabecera ilegible en {path.name}: {exc}") from exc
    return detect_source_schema(header)


def ensure_marker(marker_path: Path) -> None:
    """Verifica el marker del volumen canónico antes de escribir en /srv/data."""
    if not marker_path.is_file():
        raise MarkerError(f"marker ausente: {marker_path}")
    first_line = marker_path.read_text(encoding="utf-8").splitlines()[:1]
    if not first_line or first_line[0].strip() != MARKER_EXPECTED_FIRST_LINE:
        raise MarkerError(f"marker inválido en {marker_path}")


def load_manifest(symbol_dir: Path) -> dict[str, object]:
    path = symbol_dir / "manifest.json"
    if not path.exists():
        return {"files": {}, "schema_version": BRONZE_SCHEMA_VERSION}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BronzeError(f"manifest ilegible: {path}") from exc
    if not isinstance(loaded, dict) or not isinstance(loaded.get("files"), dict):
        raise BronzeError(f"manifest con estructura inválida: {path}")
    return loaded


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def _write_manifest(symbol_dir: Path, manifest: dict[str, object]) -> None:
    target = symbol_dir / "manifest.json"
    tmp = symbol_dir / "manifest.json.part"
    tmp.write_bytes(_manifest_bytes(manifest))
    os.replace(tmp, target)


def _append_ops(symbol_dir: Path, event: dict[str, object]) -> None:
    payload = {"at": datetime.now(UTC).isoformat(), **event}
    with (symbol_dir / "ops-downloads.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _resolve_fetcher(fetcher: Fetcher | None) -> Fetcher:
    return urllib_fetch if fetcher is None else fetcher


@dataclass(frozen=True)
class SchemaBackfillResult:
    scanned: int
    changed: int
    v1: int
    v2: int


def backfill_source_schema(symbol_dir: Path) -> SchemaBackfillResult:
    """Corrige ``schema_version`` por archivo a partir del header real (M9-A1).

    Solo reescribe ``manifest.json`` (atómico y determinista) cuando alguna
    entrada quedó con un ``schema_version`` que no coincide con el archivo:
    NUNCA toca los ``.csv.gz``. Falla cerrado ante cualquier header
    desconocido, raw ausente o raw cuyo hash no coincida con el manifiesto.
    """
    manifest = load_manifest(symbol_dir)
    files = manifest["files"]
    assert isinstance(files, dict)
    scanned = 0
    changed = 0
    v1 = 0
    v2 = 0
    for name in sorted(files):
        entry = files[name]
        if not isinstance(entry, dict):
            raise BronzeError(f"entrada inválida en manifest Bronze: {name!r}")
        day_raw = entry.get("date")
        symbol = entry.get("symbol")
        recorded_sha = entry.get("sha256")
        if (
            not isinstance(day_raw, str)
            or not isinstance(symbol, str)
            or not isinstance(recorded_sha, str)
        ):
            raise BronzeError(f"entrada Bronze incompleta: {name!r}")
        try:
            day = date.fromisoformat(day_raw)
        except ValueError as exc:
            raise BronzeError(f"fecha inválida en manifest Bronze: {name!r}") from exc
        ensure_development_day(day)
        validate_filename(name, symbol, day)
        path = symbol_dir / f"date={day_raw}" / name
        if not path.is_file():
            raise HashConflictError(f"{name}: archivo Bronze ausente: {path}")
        local_sha = sha256_file(path)
        if local_sha != recorded_sha:
            raise HashConflictError(f"{name}: hash local {local_sha} != manifest {recorded_sha!r}")
        schema = read_source_schema(path)
        scanned += 1
        if schema == SOURCE_SCHEMA_V1:
            v1 += 1
        else:
            v2 += 1
        if entry.get("schema_version") != schema:
            entry["schema_version"] = schema
            changed += 1
    if changed:
        manifest["files"] = dict(sorted(files.items()))
        _write_manifest(symbol_dir, manifest)
        _append_ops(
            symbol_dir,
            {"event": "schema_backfill", "changed": changed, "v1": v1, "v2": v2},
        )
    return SchemaBackfillResult(scanned=scanned, changed=changed, v1=v1, v2=v2)


def download_day(
    symbol_dir: Path,
    symbol: str,
    day: date,
    *,
    fetcher: Fetcher | None = None,
    base_url: str = DEFAULT_BASE_URL,
    scope: IngestScope = DEFAULT_INGEST_SCOPE,
) -> DownloadResult:
    """Descarga (u omite) un día de Bronze. Split guard ANTES de la red.

    ``scope`` es la autorización explícita de acceso; por defecto solo DEVELOPMENT.
    """
    ensure_ingest_allowed(day, scope=scope)

    name = bronze_filename(symbol, day)
    validate_filename(name, symbol, day)
    url = source_url(base_url, symbol, day)

    manifest = load_manifest(symbol_dir)
    files = manifest["files"]
    assert isinstance(files, dict)

    partition = symbol_dir / f"date={day.isoformat()}"
    final = partition / name

    if final.exists():
        local_sha = sha256_file(final)
        entry = files.get(name)
        if not isinstance(entry, dict):
            raise HashConflictError(f"{name} existe sin entrada en manifest.json")
        recorded = entry.get("sha256")
        if recorded != local_sha:
            raise HashConflictError(f"{name}: hash local {local_sha} != manifest {recorded!r}")
        _append_ops(symbol_dir, {"event": "skipped", "filename": name, "sha256": local_sha})
        return DownloadResult(name, "skipped", local_sha, final.stat().st_size)

    partition.mkdir(parents=True, exist_ok=True)
    part = final.with_name(final.name + ".part")
    do_fetch = _resolve_fetcher(fetcher)
    do_fetch(url, part)

    try:
        validate_gzip_file(part)
        source_schema = read_source_schema(part)
    except (InvalidGzipError, SourceSchemaError):
        part.unlink(missing_ok=True)
        if partition.is_dir() and not any(partition.iterdir()):
            partition.rmdir()
        raise

    payload_sha = sha256_file(part)
    payload_bytes = part.stat().st_size

    files[name] = {
        "bytes": payload_bytes,
        "date": day.isoformat(),
        "filename": name,
        "market": "spot",
        "schema_version": source_schema,
        "sha256": payload_sha,
        "source_url": url,
        "symbol": symbol,
    }
    manifest["files"] = dict(sorted(files.items()))
    _write_manifest(symbol_dir, manifest)
    os.replace(part, final)
    _append_ops(symbol_dir, {"event": "downloaded", "filename": name, "sha256": payload_sha})
    return DownloadResult(name, "downloaded", payload_sha, payload_bytes)


def download_days(
    symbol_dir: Path,
    symbol: str,
    days: Iterable[date],
    *,
    fetcher: Fetcher | None = None,
    base_url: str = DEFAULT_BASE_URL,
    scope: IngestScope = DEFAULT_INGEST_SCOPE,
) -> list[DownloadResult]:
    symbol_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadResult] = []
    for day in days:
        results.append(
            download_day(symbol_dir, symbol, day, fetcher=fetcher, base_url=base_url, scope=scope)
        )
    return results
