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
    BronzeError,
    HashConflictError,
    bronze_filename,
    load_manifest,
    sha256_file,
    validate_filename,
    validate_gzip_file,
)
from infrastructure.medallion.split_guard import ensure_development_day

__all__ = [
    "BRONZE_HEADER",
    "ORDERING_FIDELITY",
    "SILVER_SCHEMA_VERSION",
    "SILVER_HEADER",
    "InvalidRowError",
    "SilverError",
    "SilverResult",
    "transform_day",
    "transform_days",
]

SILVER_SCHEMA_VERSION = "bybit-spot-trades-silver-v1"
ORDERING_FIDELITY = "PARTIAL"
BRONZE_HEADER = ("id", "timestamp", "price", "volume", "side")
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
) -> tuple[list[tuple[str, str, str, str, str, str]], int, int, bool]:
    """Valida y lee todas las filas; FAIL CLOSED ante la primera fila inválida.

    Devuelve ``(rows, min_ts, max_ts, source_order_preserved)`` donde
    ``source_order_preserved`` es ``True`` si las filas de origen ya estaban en
    orden (timestamp) no decreciente — es decir, el orden canónico coincide
    exactamente con el orden físico publicado.
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
        if header != BRONZE_HEADER:
            raise InvalidRowError(f"{source_file}: header {header} != {BRONZE_HEADER}")
        for row_number, row in enumerate(reader, start=1):
            if len(row) != 5:
                raise InvalidRowError(f"{source_file}:{row_number}: {len(row)} columnas != 5")
            native_id, timestamp, price, quantity, taker_side = row
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
    return rows, min_ts, max_ts, source_order_preserved


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
) -> SilverResult:
    """Transforma una partición Bronze → Silver. Determinista e idempotente."""
    ensure_development_day(day)

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

    rows, min_ts, max_ts, source_order_preserved = _read_bronze_rows(bronze_path, partition)

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
) -> list[SilverResult]:
    # El split guard de cada día corre ANTES de crear el directorio destino.
    return [transform_day(bronze_dir, silver_dir, symbol, day) for day in days]
