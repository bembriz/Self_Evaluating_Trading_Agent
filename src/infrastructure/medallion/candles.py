"""Capa Silver: candles multi-timeframe deterministas desde Silver trades.

Invariantes (skill medallion-market-data + ADR-0005/0007 + reglas M5):

- Derivadas SOLO de Silver trades (la API Kline es solo reconciliación y no se
  usa aquí; un dataset de candles descargado nunca es canónico).
- Ventana calendario UTC ``[open_time, close_time)``; los 7 timeframes
  (``1m 5m 15m 30m 1h 4h 1d``) dividen 86 400 000 ms ⇒ ninguna vela cruza la
  frontera del archivo diario fuente.
- SOLO velas con al menos una operación: sin gap filling ni velas sintéticas;
  toda vela emitida está cerrada dentro del día completo de la fuente
  (``close_time <= fin del día``) ⇒ confirmadas.
- OHLC según el orden canónico de Silver ``(event_timestamp,
  source_row_number)``: open/close = primera/última operación; high/low por
  comparación Decimal exacta con desempate en la primera aparición
  (determinista).
- ``volume`` = suma ``Decimal`` exacta (nunca float) en notación fija;
  precios preservados byte-a-byte del origen.
- Guard del hash del trades Silver contra su manifest + ``row_count`` antes de
  leer (FAIL CLOSED); filas fuera de esquema/orden/día ⇒ FAIL CLOSED.
- Escritura ``.part`` + round-trip + manifest atómico + rename atómico; misma
  entrada ⇒ mismo SHA-256 de salida.
- Split guard DEVELOPMENT antes de tocar nada. No se lee Bronze.
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
from decimal import Decimal
from pathlib import Path

from infrastructure.medallion.bronze import (
    BronzeError,
    HashConflictError,
    bronze_filename,
    load_manifest,
    sha256_file,
    validate_gzip_file,
)
from infrastructure.medallion.silver import SILVER_HEADER, SILVER_SCHEMA_VERSION
from infrastructure.medallion.split_guard import (
    DEFAULT_INGEST_SCOPE,
    IngestScope,
    ensure_ingest_allowed,
)

__all__ = [
    "CANDLE_HEADER",
    "CANDLE_SCHEMA_VERSION",
    "DURATION_MS",
    "TIMEFRAMES",
    "CandleError",
    "CandleResult",
    "InvalidTradeRowError",
    "transform_day",
    "transform_days",
]

CANDLE_SCHEMA_VERSION = "bybit-spot-candles-silver-v1"
TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")
DURATION_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}
DAY_MS = 86_400_000
CANDLE_HEADER = (
    "open_time",
    "close_time",
    "symbol",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
)
_VALID_SIDES = frozenset({"buy", "sell"})
_RX_UINT = re.compile(r"^[0-9]+$")
_RX_DEC = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_RX_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CandleError(BronzeError):
    """Error base de la capa de candles (fail closed)."""


class InvalidTradeRowError(CandleError):
    """Fila de trades Silver inválida: nada se escribe sin output."""


@dataclass(frozen=True)
class CandleResult:
    filename: str
    timeframe: str
    status: str  # "transformed" | "skipped"
    sha256: str
    candles: int


@dataclass
class _Agg:
    open: str
    high: str
    high_d: Decimal
    low: str
    low_d: Decimal
    close: str
    volume: Decimal
    count: int


def _candles_manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def _write_candles_manifest(candles_dir: Path, manifest: dict[str, object]) -> None:
    tmp = candles_dir / "manifest.json.part"
    tmp.write_bytes(_candles_manifest_bytes(manifest))
    os.replace(tmp, candles_dir / "manifest.json")


def _append_ops(candles_dir: Path, event: dict[str, object]) -> None:
    payload = {"at": datetime.now(UTC).isoformat(), **event}
    with (candles_dir / "ops-candles.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _day_bounds_ms(day: date) -> tuple[int, int]:
    start = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) * 1000
    return start, start + DAY_MS


def _read_trades(
    trades_path: Path,
    source_file: str,
    symbol: str,
    day_start_ms: int,
    day_end_ms: int,
    expected_rows: int,
) -> list[tuple[int, str, str]]:
    """Valida y lee el trades Silver; FAIL CLOSED ante la primera anomalía."""
    validate_gzip_file(trades_path)
    rows: list[tuple[int, str, str]] = []
    prev_key: tuple[int, int] | None = None
    with gzip.open(trades_path, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise InvalidTradeRowError(f"{source_file}: archivo vacío") from exc
        if header != SILVER_HEADER:
            raise InvalidTradeRowError(f"{source_file}: header {header} != {SILVER_HEADER}")
        for row_number, row in enumerate(reader, start=1):
            if len(row) != 10:
                raise InvalidTradeRowError(f"{source_file}:{row_number}: {len(row)} columnas")
            (
                timestamp,
                row_symbol,
                price,
                quantity,
                taker_side,
                native_id,
                native_seq,
                src_file,
                src_sha,
                src_rn,
            ) = row
            if not _RX_UINT.match(timestamp):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: timestamp")
            if row_symbol != symbol:
                raise InvalidTradeRowError(f"{source_file}:{row_number}: symbol {row_symbol!r}")
            if not _RX_DEC.match(price):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: price {price!r}")
            if not _RX_DEC.match(quantity):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: quantity {quantity!r}")
            if taker_side not in _VALID_SIDES:
                raise InvalidTradeRowError(f"{source_file}:{row_number}: side {taker_side!r}")
            if not _RX_UINT.match(native_id):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: native_trade_id")
            if native_seq != "" and not _RX_UINT.match(native_seq):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: native_sequence")
            if src_file != source_file:
                raise InvalidTradeRowError(f"{source_file}:{row_number}: source_file {src_file!r}")
            if not _RX_HEX64.match(src_sha):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: source_file_sha256")
            if not _RX_UINT.match(src_rn):
                raise InvalidTradeRowError(f"{source_file}:{row_number}: source_row_number")
            ts_i = int(timestamp)
            if not day_start_ms <= ts_i < day_end_ms:
                raise InvalidTradeRowError(
                    f"{source_file}:{row_number}: timestamp {ts_i} fuera del día"
                )
            key = (ts_i, int(src_rn))
            if prev_key is not None and key <= prev_key:
                raise InvalidTradeRowError(
                    f"{source_file}:{row_number}: orden canónico violado {key} <= {prev_key}"
                )
            prev_key = key
            rows.append((ts_i, price, quantity))
    if not rows:
        raise InvalidTradeRowError(f"{source_file}: sin filas de datos")
    if len(rows) != expected_rows:
        raise HashConflictError(f"{source_file}: row_count {len(rows)} != manifest {expected_rows}")
    return rows


def _aggregate(
    rows: list[tuple[int, str, str]],
    duration_ms: int,
    symbol: str,
    timeframe: str,
    day_start_ms: int,
    day_end_ms: int,
) -> list[tuple[str, ...]]:
    buckets: dict[int, _Agg] = {}
    for ts_i, price, quantity in rows:
        bucket = ts_i // duration_ms * duration_ms
        price_d = Decimal(price)
        agg = buckets.get(bucket)
        if agg is None:
            buckets[bucket] = _Agg(
                open=price,
                high=price,
                high_d=price_d,
                low=price,
                low_d=price_d,
                close=price,
                volume=Decimal(quantity),
                count=1,
            )
            continue
        if price_d > agg.high_d:
            agg.high = price
            agg.high_d = price_d
        if price_d < agg.low_d:
            agg.low = price
            agg.low_d = price_d
        agg.close = price
        agg.volume += Decimal(quantity)
        agg.count += 1

    candles: list[tuple[str, ...]] = []
    for open_ms in sorted(buckets):
        close_ms = open_ms + duration_ms
        if open_ms < day_start_ms or close_ms > day_end_ms:
            raise CandleError(f"vela {timeframe} [{open_ms}, {close_ms}) fuera del día fuente")
        agg = buckets[open_ms]
        candles.append(
            (
                str(open_ms),
                str(close_ms),
                symbol,
                timeframe,
                agg.open,
                agg.high,
                agg.low,
                agg.close,
                format(agg.volume, "f"),
                str(agg.count),
            )
        )
    return candles


def _write_candle_gz(output_part: Path, candles: list[tuple[str, ...]]) -> None:
    """Escribe gzip determinista (mtime=0, nombre vacío, LF, UTF-8)."""
    with (
        output_part.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as gz,
        io.TextIOWrapper(gz, encoding="utf-8", newline="") as text,
    ):
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(CANDLE_HEADER)
        writer.writerows(candles)
        text.flush()


def _verify_roundtrip(output_part: Path, expected_candles: int) -> None:
    validate_gzip_file(output_part)
    with gzip.open(output_part, "rt", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = tuple(next(reader))
        except StopIteration as exc:
            raise CandleError("candles round-trip: archivo vacío") from exc
        if header != CANDLE_HEADER:
            raise CandleError(f"candles round-trip header inválido: {header}")
        count = sum(1 for _ in reader)
    if count != expected_candles:
        raise CandleError(f"candles round-trip {count} != {expected_candles}")


def transform_day(
    trades_dir: Path,
    candles_dir: Path,
    symbol: str,
    day: date,
    *,
    scope: IngestScope = DEFAULT_INGEST_SCOPE,
) -> list[CandleResult]:
    """Genera los 7 timeframes para un día. Determinista e idempotente.

    ``scope`` es la autorización explícita de acceso; por defecto solo DEVELOPMENT.
    """
    ensure_ingest_allowed(day, scope=scope)

    trades_filename = bronze_filename(symbol, day)
    partition = f"date={day.isoformat()}/{trades_filename}"

    trades_manifest = load_manifest(trades_dir)
    if trades_manifest.get("schema_version") != SILVER_SCHEMA_VERSION:
        raise CandleError(
            f"manifest trades schema_version "
            f"{trades_manifest.get('schema_version')!r} != {SILVER_SCHEMA_VERSION!r}"
        )
    trades_files = trades_manifest["files"]
    assert isinstance(trades_files, dict)
    trades_entry = trades_files.get(trades_filename)
    if not isinstance(trades_entry, dict):
        raise HashConflictError(f"{trades_filename}: sin entrada en manifest trades")

    trades_path = trades_dir / partition
    if not trades_path.is_file():
        raise HashConflictError(f"{trades_filename}: archivo trades ausente: {trades_path}")
    trades_sha = sha256_file(trades_path)
    recorded_sha = trades_entry.get("output_sha256")
    if recorded_sha != trades_sha:
        raise HashConflictError(
            f"trades hash mismatch para {trades_filename}: "
            f"local {trades_sha} != manifest {recorded_sha!r}"
        )
    expected_rows = trades_entry.get("row_count")
    if not isinstance(expected_rows, int):
        raise HashConflictError(f"{trades_filename}: row_count ausente en manifest trades")

    day_start_ms, day_end_ms = _day_bounds_ms(day)

    candles_manifest = load_manifest(candles_dir)
    if candles_manifest.get("schema_version") != CANDLE_SCHEMA_VERSION:
        candles_manifest["schema_version"] = CANDLE_SCHEMA_VERSION
    candles_files = candles_manifest["files"]
    assert isinstance(candles_files, dict)

    pending: dict[str, tuple[str, Path, str]] = {}
    results: list[CandleResult | None] = [None] * len(TIMEFRAMES)
    for index, tf in enumerate(TIMEFRAMES):
        filename = trades_filename.replace(".csv.gz", f"_{tf}.csv.gz")
        out_partition = f"timeframe={tf}/date={day.isoformat()}/{filename}"
        output = candles_dir / out_partition
        if not output.exists():
            pending[tf] = (filename, output, out_partition)
            continue
        entry = candles_files.get(filename)
        if not isinstance(entry, dict):
            raise HashConflictError(f"{filename}: output candles sin entrada en manifest")
        local_sha = sha256_file(output)
        if entry.get("output_sha256") != local_sha:
            raise HashConflictError(
                f"{filename}: output alterado ({local_sha} != {entry.get('output_sha256')!r})"
            )
        source_trades = entry.get("source_trades")
        if not (
            isinstance(source_trades, list)
            and source_trades
            and isinstance(source_trades[0], dict)
            and source_trades[0].get("sha256") == trades_sha
        ):
            raise HashConflictError(f"{filename}: linaje Silver de entrada cambió")
        _append_ops(
            candles_dir,
            {
                "event": "skipped",
                "filename": filename,
                "timeframe": tf,
                "sha256": local_sha,
                "candles": int(entry["candle_count"]),
            },
        )
        results[index] = CandleResult(
            filename, tf, "skipped", local_sha, int(entry["candle_count"])
        )

    if pending:
        rows = _read_trades(trades_path, partition, symbol, day_start_ms, day_end_ms, expected_rows)
        # El directorio destino solo se crea tras validar toda la fuente
        # (FAIL CLOSED sin dejar árbol parcial por filas inválidas).
        candles_dir.mkdir(parents=True, exist_ok=True)
        for tf in TIMEFRAMES:
            if tf not in pending:
                continue
            filename, output, out_partition = pending[tf]
            candles = _aggregate(
                rows,
                DURATION_MS[tf],
                symbol,
                tf,
                day_start_ms,
                day_end_ms,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output_part = output.with_name(output.name + ".part")
            ok = False
            try:
                _write_candle_gz(output_part, candles)
                _verify_roundtrip(output_part, len(candles))
                output_sha = sha256_file(output_part)
                ok = True
            finally:
                if not ok:
                    output_part.unlink(missing_ok=True)
            candles_files[filename] = {
                "candle_count": len(candles),
                "date": day.isoformat(),
                "duration_ms": DURATION_MS[tf],
                "filename": filename,
                "max_open_time": int(candles[-1][0]),
                "min_open_time": int(candles[0][0]),
                "output_path": out_partition,
                "output_sha256": output_sha,
                "schema_version": CANDLE_SCHEMA_VERSION,
                "source_trades": [{"path": partition, "sha256": trades_sha}],
                "symbol": symbol,
                "timeframe": tf,
            }
            candles_manifest["files"] = dict(sorted(candles_files.items()))
            _write_candles_manifest(candles_dir, candles_manifest)
            os.replace(output_part, output)
            _append_ops(
                candles_dir,
                {
                    "event": "transformed",
                    "filename": filename,
                    "timeframe": tf,
                    "sha256": output_sha,
                    "candles": len(candles),
                },
            )
            index = TIMEFRAMES.index(tf)
            results[index] = CandleResult(filename, tf, "transformed", output_sha, len(candles))

    return [r for r in results if r is not None]


def transform_days(
    trades_dir: Path,
    candles_dir: Path,
    symbol: str,
    days: Iterable[date],
    *,
    scope: IngestScope = DEFAULT_INGEST_SCOPE,
) -> list[CandleResult]:
    return [
        result
        for day in days
        for result in transform_day(trades_dir, candles_dir, symbol, day, scope=scope)
    ]
