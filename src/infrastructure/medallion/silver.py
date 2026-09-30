"""Capa Silver: trades canónicos deterministas desde Bronze Bybit Spot.

Invariantes (skill medallion-market-data + ADR-0005/0007 + reglas M4):

- Decimal-validación (nunca float) de ``price``/``quantity``; texto de origen
  preservado byte-a-byte (precisión exacta, cero conversión numérica).
- Sin deduplicar: cada fila de origen produce una fila de salida; unicidad solo
  por ``(source_file, source_row_number)``.
- Orden total canónico: ``(event_timestamp, source_row_number)``. El archivo Spot
  histórico NO contiene ``native_sequence``/cross-sequence ⇒
  ``ORDERING_FIDELITY=PARTIAL``: ``source_row_number`` preserva exactamente el
  orden publicado por Bybit (``source_order_preserved`` calculado por
  partición), pero el orden del matching engine para eventos con igual
  timestamp no es demostrable con esta fuente.
- SHA-256 del Bronze de entrada debe coincidir con su manifest (FAIL CLOSED).
- El schema de la fuente se detecta del header real de cada archivo
  (V1 = 5 columnas, V2 = 6 columnas con ``rpi`` final) y se registra en el
  linaje como ``source_schema_version``. La salida canónica es SIEMPRE la
  misma para V1 y V2: ``rpi`` no se propaga ni se reinterpreta. Un
  ``schema_version`` de manifiesto que contradiga al archivo ⇒ FAIL CLOSED.
- Cualquier fila inválida ⇒ FAIL CLOSED sin dejar output parcial.
- Escritura ``.part`` + validación round-trip + manifest atómico + rename
  atómico; misma entrada ⇒ mismo SHA-256 de salida.
- Split guard DEVELOPMENT antes de tocar nada.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from infrastructure.medallion.bronze import (
    SOURCE_HEADERS,
    SOURCE_SCHEMA_V1,
    BronzeError,
    HashConflictError,
    SourceSchemaError,
    bronze_filename,
    detect_source_schema,
    load_manifest,
    read_source_schema,
    sha256_file,
    validate_filename,
    validate_gzip_file,
)
from infrastructure.medallion.split_guard import (
    DEFAULT_INGEST_SCOPE,
    IngestScope,
    ensure_development_day,
    ensure_ingest_allowed,
)

__all__ = [
    "BRONZE_HEADER",
    "ORDERING_FIDELITY",
    "SILVER_SCHEMA_VERSION",
    "SILVER_HEADER",
    "InvalidRowError",
    "SilverError",
    "SilverResult",
    "SilverSchemaBackfillResult",
    "backfill_source_schema",
    "transform_day",
    "transform_days",
]

SILVER_SCHEMA_VERSION = "bybit-spot-trades-silver-v1"
ORDERING_FIDELITY = "PARTIAL"
# Compatibilidad: el header histórico de 5 columnas es el schema V1 de la fuente.
BRONZE_HEADER = SOURCE_HEADERS[SOURCE_SCHEMA_V1]
SILVER_HEADER = (
    "event_timestamp",
    "symbol",
    "price",
    "quantity",
    "taker_side",
    "native_trade_id",
    "native_sequence",
    "source_file",
    "source_file_sha256",
    "source_row_number",
)
_VALID_SIDES = frozenset({"buy", "sell"})
_RX_UINT = re.compile(r"^[0-9]+$")
_RX_DEC = re.compile(r"^[0-9]+(\.[0-9]+)?$")


class SilverError(BronzeError):
    """Error base de la capa Silver (fail closed)."""


class InvalidRowError(SilverError):
    """Fila de Bronze inválida: la partición completa se descarta sin output."""


@dataclass(frozen=True)
class SilverResult:
    filename: str
    status: str  # "transformed" | "skipped"
    sha256: str
    rows: int


def _silver_manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def _write_silver_manifest(symbol_dir: Path, manifest: dict[str, object]) -> None:
    tmp = symbol_dir / "manifest.json.part"
    tmp.write_bytes(_silver_manifest_bytes(manifest))
    os.replace(tmp, symbol_dir / "manifest.json")


def _append_ops(symbol_dir: Path, event: dict[str, object]) -> None:
    payload = {"at": datetime.now(UTC).isoformat(), **event}
    with (symbol_dir / "ops-transforms.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_bronze_rows(
    bronze_path: Path, source_file: str
) -> tuple[list[tuple[str, str, str, str, str, str]], int, int, bool, str]:
    """Valida y lee todas las filas; FAIL CLOSED ante la primera fila inválida.

    Detecta el schema real del archivo (V1/V2) y valida el ancho contra ese
    schema. Devuelve ``(rows, min_ts, max_ts, source_order_preserved, schema)``
    donde ``source_order_preserved`` es ``True`` si las filas de origen ya
    estaban en orden (timestamp) no decreciente — es decir, el orden canónico
    coincide exactamente con el orden físico publicado.
    """
    validate_gzip_file(bronze_path)
    rows: list[tuple[str, str, str, str, str, str]] = []
    min_ts = -1
    max_ts = -1
    prev_ts = -1
    source_order_preserved = True
    with gzip.open(bronze_path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise InvalidRowError(f"{source_file}: archivo vacío") from exc
        try:
            source_schema = detect_source_schema(header)
        except SourceSchemaError as exc:
            raise InvalidRowError(f"{source_file}: {exc}") from exc
        expected_columns = len(SOURCE_HEADERS[source_schema])
        for row_number, row in enumerate(reader, start=1):
            if len(row) != expected_columns:
                raise InvalidRowError(
                    f"{source_file}:{row_number}: {len(row)} columnas != {expected_columns}"
                )
            # ``rpi`` (solo V2) existe en el origen pero JAMÁS se propaga
            native_id, timestamp, price, quantity, taker_side = row[:5]
            if not _RX_UINT.match(native_id):
                raise InvalidRowError(f"{source_file}:{row_number}: id {native_id!r}")
            if not _RX_UINT.match(timestamp):
                raise InvalidRowError(f"{source_file}:{row_number}: timestamp {timestamp!r}")
            if not _RX_DEC.match(price):
                raise InvalidRowError(f"{source_file}:{row_number}: price {price!r}")
            if not _RX_DEC.match(quantity):
                raise InvalidRowError(f"{source_file}:{row_number}: quantity {quantity!r}")
            if taker_side not in _VALID_SIDES:
                raise InvalidRowError(f"{source_file}:{row_number}: side {taker_side!r}")
            ts_i = int(timestamp)
            if ts_i < prev_ts:
                source_order_preserved = False
            prev_ts = ts_i
            if min_ts < 0 or ts_i < min_ts:
                min_ts = ts_i
            if ts_i > max_ts:
                max_ts = ts_i
            rows.append((timestamp, price, quantity, taker_side, native_id, str(row_number)))
    if not rows:
        raise InvalidRowError(f"{source_file}: sin filas de datos")
    return rows, min_ts, max_ts, source_order_preserved, source_schema


def _write_silver_gz(
    output_part: Path,
    symbol: str,
    source_file: str,
    source_sha: str,
    rows: list[tuple[str, str, str, str, str, str]],
) -> None:
    """Escribe gzip determinista (mtime=0, nombre vacío, LF, UTF-8)."""
    ordered = sorted(rows, key=lambda r: (int(r[0]), int(r[5])))
    with (
        output_part.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as gz,
        io.TextIOWrapper(gz, encoding="utf-8", newline="") as text,
    ):
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(SILVER_HEADER)
        for timestamp, price, quantity, side, native_id, row_number in ordered:
            writer.writerow(
                [
                    timestamp,
                    symbol,
                    price,
                    quantity,
                    side,
                    native_id,
                    "",
                    source_file,
                    source_sha,
                    row_number,
                ]
            )
        text.flush()


def _verify_roundtrip(output_part: Path, expected_rows: int) -> None:
    validate_gzip_file(output_part)
    with gzip.open(output_part, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = tuple(next(reader))
        if header != SILVER_HEADER:
            raise SilverError(f"header silver round-trip inválido: {header}")
        count = sum(1 for _ in reader)
    if count != expected_rows:
        raise SilverError(f"round-trip rows {count} != {expected_rows}")


def transform_day(
    bronze_dir: Path,
    silver_dir: Path,
    symbol: str,
    day: date,
    *,
    scope: IngestScope = DEFAULT_INGEST_SCOPE,
) -> SilverResult:
    """Transforma una partición Bronze → Silver. Determinista e idempotente.

    ``scope`` es la autorización explícita de acceso; por defecto solo DEVELOPMENT.
    """
    ensure_ingest_allowed(day, scope=scope)

    name = bronze_filename(symbol, day)
    validate_filename(name, symbol, day)
    partition = f"date={day.isoformat()}/{name}"

    bronze_manifest = load_manifest(bronze_dir)
    bronze_files = bronze_manifest["files"]
    assert isinstance(bronze_files, dict)
    bronze_entry = bronze_files.get(name)
    if not isinstance(bronze_entry, dict):
        raise HashConflictError(f"{name}: sin entrada en manifest Bronze")

    bronze_path = bronze_dir / f"date={day.isoformat()}" / name
    if not bronze_path.is_file():
        raise HashConflictError(f"{name}: archivo Bronze ausente: {bronze_path}")
    bronze_sha = sha256_file(bronze_path)
    recorded_sha = bronze_entry.get("sha256")
    if recorded_sha != bronze_sha:
        raise HashConflictError(
            f"Bronze hash mismatch para {name}: local {bronze_sha} != manifest {recorded_sha!r}"
        )

    silver_dir.mkdir(parents=True, exist_ok=True)
    silver_manifest = load_manifest(silver_dir)
    if silver_manifest.get("schema_version") != SILVER_SCHEMA_VERSION:
        silver_manifest["schema_version"] = SILVER_SCHEMA_VERSION
    silver_files = silver_manifest["files"]
    assert isinstance(silver_files, dict)

    output = silver_dir / f"date={day.isoformat()}" / name
    if output.exists():
        entry = silver_files.get(name)
        if not isinstance(entry, dict):
            raise HashConflictError(f"{name}: output Silver sin entrada en manifest")
        local_sha = sha256_file(output)
        if entry.get("output_sha256") != local_sha:
            raise HashConflictError(
                f"{name}: output Silver alterado ({local_sha} != {entry.get('output_sha256')!r})"
            )
        if entry.get("source_bronze_sha256") != bronze_sha:
            raise HashConflictError(f"{name}: Bronze cambió respecto al linaje Silver registrado")
        _append_ops(silver_dir, {"event": "skipped", "filename": name})
        return SilverResult(name, "skipped", local_sha, int(entry["row_count"]))

    rows, min_ts, max_ts, source_order_preserved, source_schema = _read_bronze_rows(
        bronze_path, partition
    )
    recorded_schema = bronze_entry.get("schema_version")
    if isinstance(recorded_schema, str) and recorded_schema != source_schema:
        raise HashConflictError(
            f"{name}: schema_version manifest {recorded_schema!r} != detectado "
            f"{source_schema!r} (metadata Bronze sin backfill)"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output_part = output.with_name(output.name + ".part")
    ok = False
    try:
        _write_silver_gz(output_part, symbol, partition, bronze_sha, rows)
        _verify_roundtrip(output_part, len(rows))
        output_sha = sha256_file(output_part)
        ok = True
    finally:
        if not ok:
            output_part.unlink(missing_ok=True)

    silver_files[name] = {
        "date": day.isoformat(),
        "filename": name,
        "max_timestamp": max_ts,
        "min_timestamp": min_ts,
        "ordering_fidelity": ORDERING_FIDELITY,
        "output_path": partition,
        "output_sha256": output_sha,
        "row_count": len(rows),
        "schema_version": SILVER_SCHEMA_VERSION,
        "source_bronze_path": partition,
        "source_bronze_sha256": bronze_sha,
        "source_order_preserved": source_order_preserved,
        "source_schema_version": source_schema,
        "symbol": symbol,
    }
    silver_manifest["files"] = dict(sorted(silver_files.items()))
    _write_silver_manifest(silver_dir, silver_manifest)
    os.replace(output_part, output)
    _append_ops(silver_dir, {"event": "transformed", "filename": name, "sha256": output_sha})
    return SilverResult(name, "transformed", output_sha, len(rows))


def transform_days(
    bronze_dir: Path,
    silver_dir: Path,
    symbol: str,
    days: Iterable[date],
    *,
    scope: IngestScope = DEFAULT_INGEST_SCOPE,
) -> list[SilverResult]:
    # El split guard de cada día corre ANTES de crear el directorio destino.
    return [transform_day(bronze_dir, silver_dir, symbol, day, scope=scope) for day in days]


@dataclass(frozen=True)
class SilverSchemaBackfillResult:
    scanned: int
    changed: int
    v1: int
    v2: int


def backfill_source_schema(
    bronze_dir: Path, silver_dir: Path, symbol: str
) -> SilverSchemaBackfillResult:
    """Completa ``source_schema_version`` de las entradas Silver existentes (M9-A1).

    Lee el header REAL del Bronze de origen (no reinterpreta), verifica que el
    linaje ``source_bronze_sha256`` siga vigente y reescribe SOLO
    ``manifest.json`` de forma atómica: NUNCA toca los ``.csv.gz`` Silver ya
    transformados.
    """
    manifest = load_manifest(silver_dir)
    files = manifest["files"]
    assert isinstance(files, dict)
    scanned = 0
    changed = 0
    v1 = 0
    v2 = 0
    for name in sorted(files):
        entry = files[name]
        if not isinstance(entry, dict):
            raise BronzeError(f"entrada inválida en manifest Silver: {name!r}")
        day_raw = entry.get("date")
        source_path = entry.get("source_bronze_path")
        recorded_sha = entry.get("source_bronze_sha256")
        if (
            not isinstance(day_raw, str)
            or not isinstance(source_path, str)
            or not isinstance(recorded_sha, str)
        ):
            raise BronzeError(f"entrada Silver incompleta: {name!r}")
        try:
            day = date.fromisoformat(day_raw)
        except ValueError as exc:
            raise BronzeError(f"fecha inválida en manifest Silver: {name!r}") from exc
        ensure_development_day(day)
        validate_filename(name, symbol, day)
        if source_path.startswith("/") or ".." in source_path.split("/"):
            raise BronzeError(f"source_bronze_path inválido: {source_path!r}")
        bronze_path = bronze_dir / source_path
        if not bronze_path.is_file():
            raise HashConflictError(f"{name}: Bronze de origen ausente: {bronze_path}")
        local_sha = sha256_file(bronze_path)
        if local_sha != recorded_sha:
            raise HashConflictError(
                f"{name}: Bronze de origen alterado ({local_sha} != {recorded_sha!r})"
            )
        schema = read_source_schema(bronze_path)
        scanned += 1
        if schema == SOURCE_SCHEMA_V1:
            v1 += 1
        else:
            v2 += 1
        if entry.get("source_schema_version") != schema:
            entry["source_schema_version"] = schema
            changed += 1
    if changed:
        manifest["files"] = dict(sorted(files.items()))
        _write_silver_manifest(silver_dir, manifest)
        _append_ops(
            silver_dir,
            {"event": "schema_backfill", "changed": changed, "v1": v1, "v2": v2},
        )
    return SilverSchemaBackfillResult(scanned=scanned, changed=changed, v1=v1, v2=v2)
