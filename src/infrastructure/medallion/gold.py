"""Capa Gold: dataset de replay inmutable que referencia Silver (sin copiar datos).

Invariantes (skill medallion-market-data + ADR-0005/0007 + reglas M6):

- Gold **no duplica** datos de mercado: solo ``manifest.json`` +
  ``replay-config.json`` con hashes de referencia (Silver trades + candles).
- Split guard DEVELOPMENT **antes** de leer nada; ``WALK_FORWARD_READS=0``,
  ``FINAL_HOLDOUT_READS=0``.
- Validación FAIL CLOSED antes de crear Gold: hash de cada trades/candle contra
  su manifest, partición/celda ausente, schema_version, y **linaje
  candles → Silver trades** (``source_trades`` == ``(path, sha256)`` de la
  partición del día).
- ``dataset_id`` content-addressed: SHA-256 de un canonical identity payload
  SIN campos de reloj (mismo contenido ⇒ mismo id).
- Archivos deterministas sin wall-clock; timestamps solo en ``ops-gold.jsonl``
  (log separado, fuera del directorio del dataset).
- Escritura ``.part`` + round-trip + ``rename`` atómico. Dataset existente
  idéntico ⇒ SKIP; mismo ``dataset_id`` con contenido distinto ⇒ FAIL CLOSED.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from infrastructure.medallion.bronze import (
    BronzeError,
    bronze_filename,
    sha256_file,
)
from infrastructure.medallion.candles import CANDLE_SCHEMA_VERSION, TIMEFRAMES
from infrastructure.medallion.silver import SILVER_SCHEMA_VERSION
from infrastructure.medallion.split_guard import ensure_development_day

__all__ = [
    "DATASET_ID_PREFIX",
    "GOLD_MANIFEST_VERSION",
    "MANIFEST_FILENAME",
    "OPS_FILENAME",
    "REPLAY_CONFIG_FILENAME",
    "REPLAY_CONFIG_VERSION",
    "DatasetConflictError",
    "GoldError",
    "GoldResult",
    "InputHashMismatchError",
    "LineageMismatchError",
    "build_replay_config",
    "compute_dataset_id",
    "create_dataset",
]

GOLD_MANIFEST_VERSION = "gold-replay-dataset-v1"
REPLAY_CONFIG_VERSION = "replay-config-v1"
DATASET_ID_PREFIX = "gold-replay-"
MANIFEST_FILENAME = "manifest.json"
REPLAY_CONFIG_FILENAME = "replay-config.json"
OPS_FILENAME = "ops-gold.jsonl"
ALLOWED_SPLIT = "DEVELOPMENT"
_VALID_FIDELITY = frozenset({"FULL", "PARTIAL"})


class GoldError(BronzeError):
    """Error base de la capa Gold (fail closed)."""


class InputHashMismatchError(GoldError):
    """Hash de un insumo Silver no coincide con su manifest."""


class LineageMismatchError(GoldError):
    """Linaje candles → Silver trades violado."""


class DatasetConflictError(GoldError):
    """dataset_id existente con contenido distinto al recomputado."""


@dataclass(frozen=True)
class GoldResult:
    dataset_id: str
    status: str  # "created" | "skipped"
    manifest_sha256: str
    trade_partitions: int
    candle_outputs: int


@dataclass(frozen=True)
class _Sources:
    trades_schema: str
    candles_schema: str
    ordering_fidelity: str
    source_order_preserved: bool
    partitions: list[dict[str, object]]
    outputs: list[dict[str, object]]
    candle_count_by_timeframe: dict[str, int]


def _canonical_bytes(payload: Mapping[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def build_replay_config() -> dict[str, object]:
    """Config de replay fija (sin parámetros de estrategia ni de riesgo)."""
    return {
        "config_version": REPLAY_CONFIG_VERSION,
        "decision_timeframe": "15m",
        "context_timeframes": ["1h", "4h"],
        "execution_source": "silver_trades",
        "execution_model": "TRADE_SEQUENCE_TAKER_PROXY",
        "candle_visibility": "confirmed_close_only",
        "decision_rule": "decision occurs after the confirmed candle close",
        "fill_rule": "first eligible trade from the decision timestamp",
        "limitations": [
            "public trades do not model bid/ask",
            "public trades do not model depth",
            "public trades do not model queue",
            "public trades do not model market impact",
            "public trades do not model latency",
        ],
        "strategy_params_included": False,
        "risk_params_included": False,
    }


def compute_dataset_id(identity: Mapping[str, object]) -> str:
    """dataset_id determinista: content-addressed sobre el identity canónico."""
    return DATASET_ID_PREFIX + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def _load_required_manifest(symbol_dir: Path) -> dict[str, object]:
    path = symbol_dir / MANIFEST_FILENAME
    if not path.is_file():
        raise GoldError(f"manifest ausente: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GoldError(f"manifest ilegible: {path}") from exc
    if not isinstance(loaded, dict) or not isinstance(loaded.get("files"), dict):
        raise GoldError(f"manifest con estructura inválida: {path}")
    return loaded


def _require_entry(files: dict[str, object], name: str, what: str) -> dict[str, object]:
    entry = files.get(name)
    if not isinstance(entry, dict):
        raise GoldError(f"{name}: sin entrada en manifest {what}")
    return entry


def _require_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoldError(f"{what}: entero >= 0 esperado, obtenido {value!r}")
    return value


def _verify_hash(path: Path, recorded: object, what: str) -> str:
    if not isinstance(recorded, str) or len(recorded) != 64:
        raise GoldError(f"{what}: output_sha256 inválido {recorded!r}")
    if not path.is_file():
        raise GoldError(f"{what}: archivo ausente: {path}")
    actual = sha256_file(path)
    if actual != recorded:
        raise InputHashMismatchError(f"{what}: hash mismatch manifest={recorded} actual={actual}")
    return actual


def _collect_sources(
    trades_dir: Path,
    candles_dir: Path,
    symbol: str,
    dates: list[date],
) -> _Sources:
    """Valida hashes + linaje de todo lo referenciado (FAIL CLOSED)."""
    trades_manifest = _load_required_manifest(trades_dir)
    if trades_manifest.get("schema_version") != SILVER_SCHEMA_VERSION:
        raise GoldError(
            f"trades schema_version {trades_manifest.get('schema_version')!r} "
            f"!= {SILVER_SCHEMA_VERSION!r}"
        )
    trades_files = trades_manifest["files"]
    assert isinstance(trades_files, dict)

    partitions: list[dict[str, object]] = []
    fidelity_values: set[str] = set()
    sop_values: set[bool] = set()
    trades_sha_by_date: dict[str, tuple[str, str]] = {}

    for day in dates:
        day_iso = day.isoformat()
        name = bronze_filename(symbol, day)
        partition = f"date={day_iso}/{name}"
        entry = _require_entry(trades_files, name, "trades")
        fidelity = entry.get("ordering_fidelity")
        if fidelity not in _VALID_FIDELITY:
            raise GoldError(f"{name}: ordering_fidelity inválida {fidelity!r}")
        fidelity_values.add(str(fidelity))
        sop = entry.get("source_order_preserved")
        if not isinstance(sop, bool):
            raise GoldError(f"{name}: source_order_preserved inválida {sop!r}")
        sop_values.add(sop)
        row_count = _require_int(entry.get("row_count"), f"{name}.row_count")
        path = trades_dir / partition
        sha = _verify_hash(path, entry.get("output_sha256"), name)
        partitions.append(
            {"date": day_iso, "path": partition, "sha256": sha, "row_count": row_count}
        )
        trades_sha_by_date[day_iso] = (partition, sha)

    if len(fidelity_values) != 1:
        raise GoldError(f"ordering_fidelity mixta entre particiones: {fidelity_values}")

    candles_manifest = _load_required_manifest(candles_dir)
    if candles_manifest.get("schema_version") != CANDLE_SCHEMA_VERSION:
        raise GoldError(
            f"candles schema_version {candles_manifest.get('schema_version')!r} "
            f"!= {CANDLE_SCHEMA_VERSION!r}"
        )
    candles_files = candles_manifest["files"]
    assert isinstance(candles_files, dict)

    outputs: list[dict[str, object]] = []
    by_tf: dict[str, int] = {tf: 0 for tf in TIMEFRAMES}
    for day in dates:
        day_iso = day.isoformat()
        trades_path, trades_sha = trades_sha_by_date[day_iso]
        expected_lineage = [{"path": trades_path, "sha256": trades_sha}]
        for tf in TIMEFRAMES:
            name = f"{symbol}_{day_iso}_{tf}.csv.gz"
            rel = f"timeframe={tf}/date={day_iso}/{name}"
            entry = _require_entry(candles_files, name, "candles")
            lineage = entry.get("source_trades")
            if lineage != expected_lineage:
                raise LineageMismatchError(
                    f"{name}: source_trades {lineage!r} != {expected_lineage!r}"
                )
            candle_count = _require_int(entry.get("candle_count"), f"{name}.candle_count")
            path = candles_dir / rel
            sha = _verify_hash(path, entry.get("output_sha256"), name)
            outputs.append(
                {
                    "date": day_iso,
                    "timeframe": tf,
                    "path": rel,
                    "sha256": sha,
                    "candle_count": candle_count,
                }
            )
            by_tf[tf] += candle_count

    return _Sources(
        trades_schema=SILVER_SCHEMA_VERSION,
        candles_schema=CANDLE_SCHEMA_VERSION,
        ordering_fidelity=next(iter(fidelity_values)),
        source_order_preserved=all(sop_values),
        partitions=partitions,
        outputs=outputs,
        candle_count_by_timeframe=by_tf,
    )


def _build_identity(
    symbol: str,
    dates: list[date],
    sources: _Sources,
    config: Mapping[str, object],
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "dates": [d.isoformat() for d in dates],
        "trades_schema_version": sources.trades_schema,
        "candles_schema_version": sources.candles_schema,
        "ordering_fidelity": sources.ordering_fidelity,
        "source_order_preserved": sources.source_order_preserved,
        "trade_partitions": sources.partitions,
        "candle_outputs": sources.outputs,
        "replay_config": dict(config),
    }


def _source_roots(trades_dir: Path, candles_dir: Path) -> dict[str, str]:
    common = Path(os.path.commonpath([str(trades_dir.resolve()), str(candles_dir.resolve())]))
    return {
        "trades": trades_dir.resolve().relative_to(common).as_posix(),
        "candles": candles_dir.resolve().relative_to(common).as_posix(),
    }


def _build_manifest(
    dataset_id: str,
    symbol: str,
    dates: list[date],
    sources: _Sources,
    config_bytes: bytes,
    source_roots: Mapping[str, str],
) -> dict[str, object]:
    return {
        "manifest_version": GOLD_MANIFEST_VERSION,
        "dataset_id": dataset_id,
        "symbol": symbol,
        "allowed_split": ALLOWED_SPLIT,
        "date_range": {"start": dates[0].isoformat(), "end": dates[-1].isoformat()},
        "dates": [d.isoformat() for d in dates],
        "timeframes": list(TIMEFRAMES),
        "source_roots": dict(source_roots),
        "trades": {
            "schema_version": sources.trades_schema,
            "ordering_fidelity": sources.ordering_fidelity,
            "source_order_preserved": sources.source_order_preserved,
            "partitions": sources.partitions,
        },
        "candles": {
            "schema_version": sources.candles_schema,
            "outputs": sources.outputs,
            "candle_count_by_timeframe": sources.candle_count_by_timeframe,
        },
        "lineage": {
            "verified": True,
            "rule": "candles.source_trades == trades partition (path, sha256) per date",
            "trade_partitions_referenced": len(sources.partitions),
            "candle_outputs_referenced": len(sources.outputs),
        },
        "replay_config": {
            "filename": REPLAY_CONFIG_FILENAME,
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
        },
    }


def _append_ops(dest_dir: Path, event: Mapping[str, object]) -> None:
    payload = {"at": datetime.now(UTC).isoformat(), **event}
    with (dest_dir / OPS_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _verify_roundtrip(part_dir: Path, manifest_bytes: bytes, config_bytes: bytes) -> None:
    if (part_dir / MANIFEST_FILENAME).read_bytes() != manifest_bytes:
        raise GoldError("round-trip manifest.json fallido")
    if (part_dir / REPLAY_CONFIG_FILENAME).read_bytes() != config_bytes:
        raise GoldError("round-trip replay-config.json fallido")


def create_dataset(
    trades_dir: Path,
    candles_dir: Path,
    dest_dir: Path,
    symbol: str,
    days: Iterable[date],
) -> GoldResult:
    """Valida Silver y crea (o revalida) el dataset Gold de replay."""
    dates = sorted(set(days))
    if not dates:
        raise GoldError("se requiere al menos una fecha")
    for day in dates:
        ensure_development_day(day)

    config = build_replay_config()
    sources = _collect_sources(trades_dir, candles_dir, symbol, dates)
    identity = _build_identity(symbol, dates, sources, config)
    dataset_id = compute_dataset_id(identity)
    config_bytes = _canonical_bytes(config)
    manifest = _build_manifest(
        dataset_id,
        symbol,
        dates,
        sources,
        config_bytes,
        _source_roots(trades_dir, candles_dir),
    )
    manifest_bytes = _canonical_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

    final_dir = dest_dir / dataset_id
    if final_dir.exists():
        stored_manifest = final_dir / MANIFEST_FILENAME
        stored_config = final_dir / REPLAY_CONFIG_FILENAME
        if (
            not stored_manifest.is_file()
            or not stored_config.is_file()
            or stored_manifest.read_bytes() != manifest_bytes
            or stored_config.read_bytes() != config_bytes
        ):
            raise DatasetConflictError(
                f"dataset_id {dataset_id} existente con contenido distinto al "
                f"recomputado (FAIL CLOSED)"
            )
        _append_ops(
            dest_dir,
            {
                "dataset_id": dataset_id,
                "status": "skipped",
                "symbol": symbol,
                "dates": [d.isoformat() for d in dates],
                "manifest_sha256": manifest_sha,
            },
        )
        return GoldResult(
            dataset_id=dataset_id,
            status="skipped",
            manifest_sha256=manifest_sha,
            trade_partitions=len(sources.partitions),
            candle_outputs=len(sources.outputs),
        )

    part_dir = dest_dir / f"{dataset_id}.part"
    if part_dir.exists():
        shutil.rmtree(part_dir)
    part_dir.mkdir(parents=True)
    try:
        (part_dir / MANIFEST_FILENAME).write_bytes(manifest_bytes)
        (part_dir / REPLAY_CONFIG_FILENAME).write_bytes(config_bytes)
        _verify_roundtrip(part_dir, manifest_bytes, config_bytes)
        os.replace(part_dir, final_dir)
    except BaseException:
        shutil.rmtree(part_dir, ignore_errors=True)
        raise

    _append_ops(
        dest_dir,
        {
            "dataset_id": dataset_id,
            "status": "created",
            "symbol": symbol,
            "dates": [d.isoformat() for d in dates],
            "manifest_sha256": manifest_sha,
        },
    )
    return GoldResult(
        dataset_id=dataset_id,
        status="created",
        manifest_sha256=manifest_sha,
        trade_partitions=len(sources.partitions),
        candle_outputs=len(sources.outputs),
    )
