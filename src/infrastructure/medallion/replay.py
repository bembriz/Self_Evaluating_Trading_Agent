"""Trade-Level Replay — motor determinista de dos relojes (M7).

Contrato: ``docs/design/medallion-replay-architecture.md`` §8–§11 + ADR-0005.

Invariantes:

- RELOJ DE ESTRATEGIA: solo velas 15m confirmadas (close ≤ decisión) + contexto
  causal 1h/4h (cierre ≤ timestamp de decisión). Cero lookahead.
- RELOJ DE EJECUCIÓN: cada trade Silver en orden estricto. La decisión se
  materializa en el primer trade ``>= trigger``; trigger y fill nunca se
  confunden (§10).
- Orden por trade: advance (enqueue) → (a) fill de exit pendiente → (b) fills
  FIFO de decisiones → (c) evaluación de riesgo (actualiza camino, evalúa con
  trailing PRE-elevación — stop family primero que TP, alineado con
  ``paper_engine._check_exits`` — y después eleva el trailing).
- Contabilidad: ``net = gross − slippage − fees`` con
  ``gross = (exit_trade − entry_trade) × qty``,
  ``slippage = bps/1e4 × (entry_trade + exit_trade) × qty ≥ 0`` y
  ``fees = fee_rate × (entry_exec + exit_exec) × qty``.
- FAIL CLOSED: validación del dataset Gold completa (hash, linaje, id,
  traversal) antes de leer; loaders con validación ligera fila a fila.
- Sin wall-clock: mismo dataset + misma versión ⇒ payload byte-idéntico.
"""

from __future__ import annotations

import bisect
import csv
import gzip
import json
import os
import re
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from domain.market.candle import Candle
from domain.market.indicators import atr
from domain.risk.config import RiskConfig
from domain.risk.engine import PortfolioRiskState, RiskEngine, RiskVerdict, TradeProposal
from domain.risk.guards import KillSwitchState
from domain.risk.stops import initial_stop, take_profit, update_trailing
from domain.trading.signal import Action
from infrastructure.medallion.bronze import BronzeError, sha256_file
from infrastructure.medallion.candles import (
    CANDLE_HEADER,
    CANDLE_SCHEMA_VERSION,
    DURATION_MS,
    TIMEFRAMES,
)
from infrastructure.medallion.gold import (
    ALLOWED_SPLIT,
    GOLD_MANIFEST_VERSION,
    MANIFEST_FILENAME,
    REPLAY_CONFIG_FILENAME,
    REPLAY_CONFIG_VERSION,
    InputHashMismatchError,
    compute_dataset_id,
)
from infrastructure.medallion.silver import SILVER_HEADER, SILVER_SCHEMA_VERSION
from infrastructure.medallion.split_guard import ensure_development_day

__all__ = [
    "CANDLE_HEADER",
    "SILVER_HEADER",
    "DAY_MS",
    "LEDGER_VERSION",
    "EXECUTION_MODEL_VERSION",
    "EXIT_REASONS",
    "REQUIRED_RECORD_FIELDS",
    "DEFAULT_SCENARIO",
    "CandleFile",
    "CandleRow",
    "ContextSnapshot",
    "DatasetValidationError",
    "Decision",
    "DecisionProvider",
    "InputHashMismatchError",
    "LedgerConflictError",
    "ReplayError",
    "ReplayResult",
    "ReplayScenario",
    "ReplayTrade",
    "ScriptedScheduleProvider",
    "TradeFile",
    "ValidatedDataset",
    "iter_trades",
    "ledger_payload",
    "load_candles",
    "replay_engine",
    "validate_dataset",
    "write_ledger",
]

DAY_MS = 86_400_000
LEDGER_VERSION = "replay-ledger-v1"
EXECUTION_MODEL_VERSION = "TRADE_SEQUENCE_TAKER_PROXY-v1"
EXECUTION_MODEL = "TRADE_SEQUENCE_TAKER_PROXY"
CANDLE_VISIBILITY = "confirmed_close_only"
FILL_RULE = "first eligible trade from the decision timestamp"
PNL_BASIS = "gross_minus_slippage_minus_fees"
SWEEP_CUTOFF = 1 << 62

EXIT_REASONS = (
    "stop_loss",
    "take_profit",
    "trailing_stop",
    "strategy_exit",
    "max_time_in_position",
    "end_of_dataset",
)

REQUIRED_RECORD_FIELDS = (
    "entry_signal_timestamp",
    "entry_trigger_timestamp",
    "entry_fill_timestamp",
    "entry_reference_price",
    "entry_execution_price",
    "atr_at_entry",
    "initial_stop",
    "initial_target",
    "mfe",
    "mae",
    "highest_price",
    "exit_trigger_timestamp",
    "exit_fill_timestamp",
    "exit_reason",
    "exit_reference_price",
    "exit_execution_price",
    "quantity",
    "fees",
    "slippage",
    "gross_pnl",
    "net_pnl",
    "holding_ms",
    "strategy_version",
    "risk_version",
    "execution_model_version",
    "dataset_id",
    "dataset_sha",
)

_RX_UINT = re.compile(r"^[0-9]+$")
_RX_DEC = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_RX_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_VALID_FIDELITY = frozenset({"FULL", "PARTIAL"})
SIZING_MODES = frozenset({"fixed", "risk_engine"})
VALID_INTENSITIES = frozenset({"low", "medium", "high"})


class ReplayError(BronzeError):
    """Error base del replay de trade-level (fail closed)."""


class DatasetValidationError(ReplayError):
    """Dataset Gold inválido o incoherente con Silver (FAIL CLOSED)."""


class LedgerConflictError(ReplayError):
    """Ledger existente con contenido distinto (FAIL CLOSED)."""


# ------------------------------------------------------------------ modelos


@dataclass(frozen=True, slots=True)
class CandleRow:
    """Fila de candle Silver parseada (ventana calendario UTC)."""

    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """Contexto causal en el instante de la decisión (close ≤ decision_ts)."""

    decision_ts: int
    h1: CandleRow | None
    h4: CandleRow | None


@dataclass(frozen=True, slots=True)
class Decision:
    """Señal del provider tras un close confirmado de vela 15m."""

    action: str
    signal_ts: int
    reference_price: float
    candle_index: int
    atr: float | None


class DecisionProvider(Protocol):
    """Contrato de la estrategia (scripted en M7; LLM/ML después)."""

    def decide(
        self,
        *,
        candle_index: int,
        decision_ts: int,
        reference_price: float,
        atr_value: float | None,
        context: ContextSnapshot,
    ) -> Decision | None: ...


@dataclass(frozen=True, slots=True)
class ReplayTrade:
    """Trade Silver canónico en el reloj de ejecución."""

    ts: int
    price: float
    quantity: float


@dataclass(frozen=True, slots=True)
class TradeFile:
    """Partición Silver de trades referenciada por Gold."""

    date: date
    path: Path
    sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class CandleFile:
    """Output de candles Silver referenciado por Gold."""

    date: date
    timeframe: str
    path: Path
    sha256: str
    candle_count: int


@dataclass(frozen=True)
class ValidatedDataset:
    """Dataset Gold validado completamente (FAIL CLOSED) y listo para leer."""

    dataset_id: str
    dataset_sha: str
    symbol: str
    dates: tuple[date, ...]
    ordering_fidelity: str
    config: dict[str, object]
    trade_files: tuple[TradeFile, ...]
    candle_files: tuple[CandleFile, ...]


REPLAY_RISK = RiskConfig(
    stop_atr_multiplier=2.0,
    take_profit_r_multiple=1.5,
    trailing_atr_multiplier=1.0,
    version="replay-risk-v1",
)


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    """Escenario determinista de replay (riesgo, costes, estrategia).

    ``sizing_mode``:
      - ``"fixed"`` (legacy M7): quantity fija ``quantity``; stops/target desde
        el precio de ejecución. Output byte-idéntico al UAT M7.
      - ``"risk_engine"`` (M9-B): sizing dinámico vía ``RiskEngine.evaluate``
        en el primer trade elegible, con ``price = reference_price`` y
        ``atr`` de la decisión; stops/target desde el veredicto.
    """

    scenario_id: str = "scripted-default-v1"
    risk: RiskConfig = REPLAY_RISK
    quantity: float = 0.01
    fee_rate: float = 0.001
    slippage_bps: float = 5.0
    strategy_version: str = "scripted-schedule-v1"
    atr_period: int = 14
    sizing_mode: str = "fixed"
    intensity: str = "medium"

    def __post_init__(self) -> None:
        if self.sizing_mode not in SIZING_MODES:
            raise ValueError(
                f"sizing_mode inválido {self.sizing_mode!r}; "
                f"esperado {sorted(SIZING_MODES)} (FAIL CLOSED)"
            )
        if self.intensity not in VALID_INTENSITIES:
            raise ValueError(
                f"intensity inválida {self.intensity!r}; "
                f"esperado {sorted(VALID_INTENSITIES)} (FAIL CLOSED)"
            )


DEFAULT_SCENARIO = ReplayScenario()


@dataclass
class ReplayResult:
    """Registros trade-a-trade + contadores de la corrida."""

    records: list[dict[str, object]]
    stats: dict[str, int]
    rejected_reasons: dict[str, int] = field(default_factory=dict)


class ScriptedScheduleProvider:
    """Decisiones guionadas por índice de vela (validación de contratos)."""

    def decide(
        self,
        *,
        candle_index: int,
        decision_ts: int,
        reference_price: float,
        atr_value: float | None,
        context: ContextSnapshot,
    ) -> Decision | None:
        del context
        index = candle_index
        if index >= 14 and index % 12 == 5:
            if atr_value is None:
                return None
            return Decision(
                action="buy",
                signal_ts=decision_ts,
                reference_price=reference_price,
                candle_index=index,
                atr=atr_value,
            )
        if index >= 25 and index % 12 == 1:
            return Decision(
                action="sell",
                signal_ts=decision_ts,
                reference_price=reference_price,
                candle_index=index,
                atr=atr_value,
            )
        return None


# ------------------------------------------------------------- validación


def _dataset_error(what: str) -> DatasetValidationError:
    return DatasetValidationError(f"{what} (FAIL CLOSED)")


def _require_dict(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _dataset_error(f"{what}: objeto JSON esperado")
    return value


def _require_str(value: object, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise _dataset_error(f"{what}: cadena no vacía esperada")
    return value


def _require_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _dataset_error(f"{what}: entero >= 0 esperado")
    return value


def _require_sha(value: object, what: str) -> str:
    text = _require_str(value, what)
    if not _RX_SHA64.match(text):
        raise _dataset_error(f"{what}: sha256 inválido {text!r}")
    return text


def _require_date(value: object, what: str) -> date:
    text = _require_str(value, what)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise _dataset_error(f"{what}: fecha ISO inválida {text!r}") from exc


def _safe_relative(base: Path, rel: object, what: str) -> Path:
    text = _require_str(rel, what)
    candidate = Path(text)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise _dataset_error(f"{what}: path inseguro {text!r}")
    return base / candidate


def _read_json(path: Path, what: str) -> dict[str, object]:
    if not path.is_file():
        raise _dataset_error(f"{what}: ausente {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise _dataset_error(f"{what}: ilegible {path}") from exc
    return _require_dict(loaded, what)


def _parse_manifest_dates(manifest: Mapping[str, object]) -> tuple[date, ...]:
    raw = manifest.get("dates")
    if not isinstance(raw, list) or not raw:
        raise _dataset_error("dates: se requiere al menos una fecha")
    days: list[date] = []
    for item in raw:
        days.append(_require_date(item, "dates[]"))
    return tuple(days)


def _load_config(dataset_dir: Path, manifest: Mapping[str, object]) -> dict[str, object]:
    block = _require_dict(manifest.get("replay_config"), "replay_config")
    if block.get("filename") != REPLAY_CONFIG_FILENAME:
        raise _dataset_error(f"replay_config.filename != {REPLAY_CONFIG_FILENAME!r}")
    recorded = _require_sha(block.get("sha256"), "replay_config.sha256")
    path = dataset_dir / REPLAY_CONFIG_FILENAME
    if not path.is_file():
        raise _dataset_error(f"{REPLAY_CONFIG_FILENAME}: ausente {path}")
    actual = sha256_file(path)
    if actual != recorded:
        raise _dataset_error(
            f"{REPLAY_CONFIG_FILENAME}: hash mismatch manifest={recorded} actual={actual}"
        )
    config = _read_json(path, REPLAY_CONFIG_FILENAME)
    expected: dict[str, object] = {
        "config_version": REPLAY_CONFIG_VERSION,
        "decision_timeframe": "15m",
        "context_timeframes": ["1h", "4h"],
        "execution_source": "silver_trades",
        "execution_model": EXECUTION_MODEL,
        "candle_visibility": CANDLE_VISIBILITY,
    }
    for key, want in expected.items():
        if config.get(key) != want:
            raise _dataset_error(f"{REPLAY_CONFIG_FILENAME}.{key}={config.get(key)!r} != {want!r}")
    return config


def _check_structure(
    manifest: Mapping[str, object], dates: Sequence[date]
) -> tuple[dict[str, object], dict[str, object]]:
    if manifest.get("manifest_version") != GOLD_MANIFEST_VERSION:
        raise _dataset_error(
            f"manifest_version={manifest.get('manifest_version')!r} != {GOLD_MANIFEST_VERSION!r}"
        )
    if manifest.get("allowed_split") != ALLOWED_SPLIT:
        raise _dataset_error(
            f"allowed_split={manifest.get('allowed_split')!r} != {ALLOWED_SPLIT!r}"
        )
    _require_str(manifest.get("symbol"), "symbol")
    want_range = {"start": dates[0].isoformat(), "end": dates[-1].isoformat()}
    if manifest.get("date_range") != want_range:
        raise _dataset_error(f"date_range incoherente con dates: {manifest.get('date_range')!r}")
    if manifest.get("timeframes") != list(TIMEFRAMES):
        raise _dataset_error("timeframes incoherente con la capa de candles")
    trades_block = _require_dict(manifest.get("trades"), "trades")
    if trades_block.get("schema_version") != SILVER_SCHEMA_VERSION:
        raise _dataset_error(
            f"trades.schema_version={trades_block.get('schema_version')!r} "
            f"!= {SILVER_SCHEMA_VERSION!r}"
        )
    fidelity = trades_block.get("ordering_fidelity")
    if fidelity not in _VALID_FIDELITY:
        raise _dataset_error(f"trades.ordering_fidelity inválida {fidelity!r}")
    if not isinstance(trades_block.get("source_order_preserved"), bool):
        raise _dataset_error("trades.source_order_preserved inválida")
    partitions = trades_block.get("partitions")
    if not isinstance(partitions, list) or not partitions:
        raise _dataset_error("trades.partitions vacío")
    candles_block = _require_dict(manifest.get("candles"), "candles")
    if candles_block.get("schema_version") != CANDLE_SCHEMA_VERSION:
        raise _dataset_error(
            f"candles.schema_version={candles_block.get('schema_version')!r} "
            f"!= {CANDLE_SCHEMA_VERSION!r}"
        )
    outputs = candles_block.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise _dataset_error("candles.outputs vacío")
    return trades_block, candles_block


def _check_source_roots(
    manifest: Mapping[str, object], trades_dir: Path, candles_dir: Path
) -> None:
    common = Path(os.path.commonpath([str(trades_dir.resolve()), str(candles_dir.resolve())]))
    try:
        expected = {
            "trades": trades_dir.resolve().relative_to(common).as_posix(),
            "candles": candles_dir.resolve().relative_to(common).as_posix(),
        }
    except ValueError as exc:
        raise _dataset_error("source_roots no computables") from exc
    if manifest.get("source_roots") != expected:
        raise _dataset_error(f"source_roots={manifest.get('source_roots')!r} != {expected!r}")


def _check_lineage(manifest: Mapping[str, object], *, partitions: int, outputs: int) -> None:
    lineage = _require_dict(manifest.get("lineage"), "lineage")
    if lineage.get("verified") is not True:
        raise _dataset_error("lineage.verified no es true")
    if lineage.get("trade_partitions_referenced") != partitions:
        raise _dataset_error("lineage.trade_partitions_referenced incoherente")
    if lineage.get("candle_outputs_referenced") != outputs:
        raise _dataset_error("lineage.candle_outputs_referenced incoherente")


def _build_trade_files(
    trades_block: Mapping[str, object], trades_dir: Path, dates: Sequence[date]
) -> tuple[TradeFile, ...]:
    allowed = set(dates)
    entries = trades_block.get("partitions")
    assert isinstance(entries, list)
    files: list[TradeFile] = []
    for index, raw in enumerate(entries):
        entry = _require_dict(raw, f"trades.partitions[{index}]")
        day = _require_date(entry.get("date"), f"trades.partitions[{index}].date")
        if day not in allowed:
            raise _dataset_error(f"trades.partitions[{index}].date {day} fuera de dates")
        files.append(
            TradeFile(
                date=day,
                path=_safe_relative(
                    trades_dir, entry.get("path"), f"trades.partitions[{index}].path"
                ),
                sha256=_require_sha(entry.get("sha256"), f"trades.partitions[{index}].sha256"),
                row_count=_require_int(
                    entry.get("row_count"), f"trades.partitions[{index}].row_count"
                ),
            )
        )
    return tuple(sorted(files, key=lambda f: f.date))


def _build_candle_files(
    candles_block: Mapping[str, object], candles_dir: Path, dates: Sequence[date]
) -> tuple[CandleFile, ...]:
    allowed = set(dates)
    entries = candles_block.get("outputs")
    assert isinstance(entries, list)
    files: list[CandleFile] = []
    counts: dict[str, int] = {tf: 0 for tf in TIMEFRAMES}
    for index, raw in enumerate(entries):
        entry = _require_dict(raw, f"candles.outputs[{index}]")
        day = _require_date(entry.get("date"), f"candles.outputs[{index}].date")
        if day not in allowed:
            raise _dataset_error(f"candles.outputs[{index}].date {day} fuera de dates")
        timeframe = _require_str(entry.get("timeframe"), f"candles.outputs[{index}].timeframe")
        if timeframe not in TIMEFRAMES:
            raise _dataset_error(f"candles.outputs[{index}].timeframe desconocida {timeframe!r}")
        candle_count = _require_int(
            entry.get("candle_count"), f"candles.outputs[{index}].candle_count"
        )
        counts[timeframe] += candle_count
        files.append(
            CandleFile(
                date=day,
                timeframe=timeframe,
                path=_safe_relative(
                    candles_dir, entry.get("path"), f"candles.outputs[{index}].path"
                ),
                sha256=_require_sha(entry.get("sha256"), f"candles.outputs[{index}].sha256"),
                candle_count=candle_count,
            )
        )
    declared = candles_block.get("candle_count_by_timeframe")
    if declared is not None and declared != counts:
        raise _dataset_error(f"candles.candle_count_by_timeframe incoherente: {declared!r}")
    files.sort(key=lambda f: (f.timeframe, f.date))
    return tuple(files)


def _check_identity(
    manifest: Mapping[str, object],
    config: Mapping[str, object],
    dataset_dir: Path,
    dates: Sequence[date],
    trades_block: Mapping[str, object],
    candles_block: Mapping[str, object],
) -> str:
    identity = {
        "symbol": manifest.get("symbol"),
        "dates": [d.isoformat() for d in dates],
        "trades_schema_version": trades_block.get("schema_version"),
        "candles_schema_version": candles_block.get("schema_version"),
        "ordering_fidelity": trades_block.get("ordering_fidelity"),
        "source_order_preserved": trades_block.get("source_order_preserved"),
        "trade_partitions": trades_block.get("partitions"),
        "candle_outputs": candles_block.get("outputs"),
        "replay_config": dict(config),
    }
    recomputed = compute_dataset_id(identity)
    recorded = _require_str(manifest.get("dataset_id"), "dataset_id")
    if recomputed != recorded:
        raise _dataset_error(f"dataset_id recomputado {recomputed} != manifest {recorded}")
    if recorded != dataset_dir.name:
        raise _dataset_error(f"dataset_id {recorded} != dirname {dataset_dir.name} (FAIL CLOSED)")
    return recorded


def _verify_hashes(files: Sequence[TradeFile | CandleFile]) -> None:
    for entry in files:
        if not entry.path.is_file():
            raise _dataset_error(f"archivo referenciado ausente: {entry.path}")
        actual = sha256_file(entry.path)
        if actual != entry.sha256:
            raise InputHashMismatchError(
                f"{entry.path.name}: hash mismatch manifest={entry.sha256} actual={actual}"
            )


def validate_dataset(dataset_dir: Path, trades_dir: Path, candles_dir: Path) -> ValidatedDataset:
    """Valida el dataset Gold completo antes de leer Silver (FAIL CLOSED).

    Orden: manifest → dates → split guard (antes de tocar Silver) → config →
    estructura → source_roots → linaje → file lists (traversal) → identidad →
    hashes de las 3+21 entradas.
    """
    manifest = _read_json(dataset_dir / MANIFEST_FILENAME, MANIFEST_FILENAME)
    dates = _parse_manifest_dates(manifest)
    for day in dates:
        ensure_development_day(day)
    config = _load_config(dataset_dir, manifest)
    trades_block, candles_block = _check_structure(manifest, dates)
    _check_source_roots(manifest, trades_dir, candles_dir)
    trade_files = _build_trade_files(trades_block, trades_dir, dates)
    candle_files = _build_candle_files(candles_block, candles_dir, dates)
    _check_lineage(manifest, partitions=len(trade_files), outputs=len(candle_files))
    dataset_id = _check_identity(manifest, config, dataset_dir, dates, trades_block, candles_block)
    _verify_hashes([*trade_files, *candle_files])
    return ValidatedDataset(
        dataset_id=dataset_id,
        dataset_sha=sha256_file(dataset_dir / MANIFEST_FILENAME),
        symbol=_require_str(manifest.get("symbol"), "symbol"),
        dates=dates,
        ordering_fidelity=_require_str(
            trades_block.get("ordering_fidelity"), "trades.ordering_fidelity"
        ),
        config=config,
        trade_files=trade_files,
        candle_files=candle_files,
    )


# ------------------------------------------------------------ carga de datos


def _day_bounds_ms(day: date) -> tuple[int, int]:
    start = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) * 1000
    return start, start + DAY_MS


def _open_gzip(path: Path) -> Iterator[list[str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        yield from csv.reader(fh)


def load_candles(ds: ValidatedDataset, timeframes: Sequence[str]) -> dict[str, list[CandleRow]]:
    """Carga y valida candles por timeframe (FAIL CLOSED, orden por fecha)."""
    out: dict[str, list[CandleRow]] = {}
    for timeframe in dict.fromkeys(timeframes):
        files = [f for f in ds.candle_files if f.timeframe == timeframe]
        if not files:
            raise ReplayError(f"sin archivos de candles para {timeframe}")
        rows: list[CandleRow] = []
        prev_open: int | None = None
        for candle_file in files:
            day_start, day_end = _day_bounds_ms(candle_file.date)
            duration = DURATION_MS[timeframe]
            file_rows, prev_open = _read_candle_file(
                candle_file, ds.symbol, duration, day_start, day_end, prev_open
            )
            rows.extend(file_rows)
        out[timeframe] = rows
    return out


def _read_candle_file(
    candle_file: CandleFile,
    symbol: str,
    duration: int,
    day_start: int,
    day_end: int,
    prev_open: int | None,
) -> tuple[list[CandleRow], int | None]:
    rows: list[CandleRow] = []
    try:
        reader = _open_gzip(candle_file.path)
        header = next(reader, None)
        if header is None or tuple(header) != CANDLE_HEADER:
            raise ReplayError(
                f"{candle_file.path.name}: header {tuple(header or ())} != {CANDLE_HEADER}"
            )
        for row_number, row in enumerate(reader, start=1):
            if len(row) != len(CANDLE_HEADER):
                raise ReplayError(f"{candle_file.path.name}:{row_number}: {len(row)} columnas")
            if not _RX_UINT.match(row[0]) or not _RX_UINT.match(row[1]):
                raise ReplayError(f"{candle_file.path.name}:{row_number}: timestamps")
            open_time = int(row[0])
            close_time = int(row[1])
            if row[2] != symbol:
                raise ReplayError(f"{candle_file.path.name}:{row_number}: symbol {row[2]!r}")
            if row[3] != candle_file.timeframe:
                raise ReplayError(f"{candle_file.path.name}:{row_number}: timeframe {row[3]!r}")
            if close_time != open_time + duration:
                raise ReplayError(f"{candle_file.path.name}:{row_number}: close_time")
            if not day_start <= open_time or close_time > day_end:
                raise ReplayError(f"{candle_file.path.name}:{row_number}: fuera del día")
            for column in range(4, 9):
                if not _RX_DEC.match(row[column]):
                    raise ReplayError(f"{candle_file.path.name}:{row_number}: columna {column}")
            if not _RX_UINT.match(row[9]):
                raise ReplayError(f"{candle_file.path.name}:{row_number}: trade_count")
            open_p, high_p, low_p, close_p = (float(row[i]) for i in range(4, 8))
            if high_p < max(open_p, close_p) or low_p > min(open_p, close_p):
                raise ReplayError(f"{candle_file.path.name}:{row_number}: OHLC")
            volume_p = float(row[8])
            if volume_p < 0.0:
                raise ReplayError(f"{candle_file.path.name}:{row_number}: volume {volume_p}")
            if prev_open is not None and open_time <= prev_open:
                raise ReplayError(
                    f"{candle_file.path.name}:{row_number}: orden {open_time} <= {prev_open}"
                )
            prev_open = open_time
            rows.append(
                CandleRow(
                    open_time=open_time,
                    close_time=close_time,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=volume_p,
                    trade_count=int(row[9]),
                )
            )
    except ReplayError:
        raise
    except (OSError, EOFError, StopIteration, csv.Error, UnicodeDecodeError) as exc:
        raise ReplayError(f"{candle_file.path.name}: lectura fallida") from exc
    if len(rows) != candle_file.candle_count:
        raise ReplayError(
            f"{candle_file.path.name}: candle_count {len(rows)} != {candle_file.candle_count}"
        )
    assert prev_open is not None or not rows
    return rows, prev_open


def iter_trades(ds: ValidatedDataset) -> Iterator[ReplayTrade]:
    """Itera los trades Silver referenciados con validación ligera FAIL CLOSED."""
    declared = sum(f.row_count for f in ds.trade_files)
    seen = 0
    prev_ts: int | None = None
    for trade_file in ds.trade_files:
        try:
            reader = _open_gzip(trade_file.path)
            header = next(reader, None)
            if header is None or tuple(header) != SILVER_HEADER:
                raise ReplayError(
                    f"{trade_file.path.name}: header {tuple(header or ())} != {SILVER_HEADER}"
                )
            for row_number, row in enumerate(reader, start=1):
                if len(row) != len(SILVER_HEADER):
                    raise ReplayError(f"{trade_file.path.name}:{row_number}: {len(row)} columnas")
                if not _RX_UINT.match(row[0]):
                    raise ReplayError(f"{trade_file.path.name}:{row_number}: event_timestamp")
                ts = int(row[0])
                if row[1] != ds.symbol:
                    raise ReplayError(f"{trade_file.path.name}:{row_number}: symbol {row[1]!r}")
                if not _RX_DEC.match(row[2]) or not _RX_DEC.match(row[3]):
                    raise ReplayError(f"{trade_file.path.name}:{row_number}: price/quantity")
                price = float(row[2])
                quantity = float(row[3])
                if price <= 0.0 or quantity <= 0.0:
                    raise ReplayError(
                        f"{trade_file.path.name}:{row_number}: price/quantity no positivos"
                    )
                if prev_ts is not None and ts < prev_ts:
                    raise ReplayError(
                        f"{trade_file.path.name}:{row_number}: orden {ts} < {prev_ts}"
                    )
                prev_ts = ts
                seen += 1
                yield ReplayTrade(ts=ts, price=price, quantity=quantity)
        except ReplayError:
            raise
        except (OSError, EOFError, csv.Error, UnicodeDecodeError) as exc:
            raise ReplayError(f"{trade_file.path.name}: lectura fallida") from exc
    if seen != declared:
        raise ReplayError(f"row_count total {seen} != manifest {declared}")


# ------------------------------------------------------------------ motor


@dataclass
class _Position:
    quantity: float
    entry_signal_ts: int
    entry_trigger_ts: int
    entry_fill_ts: int
    entry_reference_price: float
    entry_execution_price: float
    entry_trade_price: float
    entry_candle_index: int
    entry_fill_trade_index: int
    atr: float
    initial_stop: float
    initial_target: float
    trailing: float
    highest: float
    lowest: float
    trailing_updates: int = 0


@dataclass
class _PendingExit:
    reason: str
    trigger_ts: int
    trigger_trade_index: int | None
    trigger_price: float
    reference_price: float


class _Engine:
    """Dos relojes: velas confirmadas → decisiones; trades → fills/riesgo."""

    def __init__(
        self,
        candles_15m: Sequence[CandleRow],
        ctx_1h: Sequence[CandleRow],
        ctx_4h: Sequence[CandleRow],
        trades: Iterable[ReplayTrade],
        scenario: ReplayScenario,
        provider: DecisionProvider,
        *,
        dataset_id: str,
        dataset_sha: str,
    ) -> None:
        self._candles = candles_15m
        self._ctx_1h = ctx_1h
        self._ctx_4h = ctx_4h
        self._trades = trades
        self._scenario = scenario
        self._provider = provider
        self._dataset_id = dataset_id
        self._dataset_sha = dataset_sha
        self._h1_keys = [c.close_time for c in ctx_1h]
        self._h4_keys = [c.close_time for c in ctx_4h]
        self._atr: list[float | None] = []
        self._records: list[dict[str, object]] = []
        self._stats = {
            "decisions_total": 0,
            "decisions_filled": 0,
            "decisions_dropped": 0,
            "decisions_unfilled": 0,
            "decisions_rejected": 0,
            "closed_trades": 0,
        }
        self._rejected_reasons: dict[str, int] = {}
        self._queue: deque[Decision] = deque()
        self._candle_i = 0
        self._position: _Position | None = None
        self._pending: _PendingExit | None = None
        self._dynamic = scenario.sizing_mode == "risk_engine"
        if self._dynamic:
            # Estado de portfolio para RiskEngine (solo modo dinámico; el modo
            # legacy fixed jamás instancia RiskEngine — byte-idéntico a M7).
            self._risk_engine = RiskEngine(scenario.risk)
            self._risk_kill = KillSwitchState()
            self._capital = scenario.risk.capital
            self._realized_total = 0.0
            self._realized_today = 0.0
            self._day: int | None = None
            self._peak_equity = scenario.risk.capital

    def run(self) -> ReplayResult:
        domain_candles = [
            Candle(
                timestamp_ms=c.open_time,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                turnover=0.0,
            )
            for c in self._candles
        ]
        self._atr = atr(domain_candles, period=self._scenario.atr_period)
        last: ReplayTrade | None = None
        last_index = -1
        for index, trade in enumerate(self._trades):
            self._advance(trade.ts)
            self._fill_pending_exit(trade, index)
            self._drain_decisions(trade, index)
            self._risk_eval(trade, index)
            last = trade
            last_index = index
        self._advance(SWEEP_CUTOFF)
        while self._queue:
            self._queue.popleft()
            self._stats["decisions_unfilled"] += 1
        if self._pending is not None:
            self._fill_pending_edge()
        if self._position is not None:
            if last is None:
                raise ReplayError("posición abierta sin trades (invariante rota)")
            position = self._position
            self._finish(
                position,
                _PendingExit(
                    reason="end_of_dataset",
                    trigger_ts=last.ts,
                    trigger_trade_index=last_index,
                    trigger_price=last.price,
                    reference_price=last.price,
                ),
                fill_ts=last.ts,
                fill_trade_index=last_index,
                fill_trade_price=last.price,
            )
        return ReplayResult(
            records=self._records,
            stats=dict(self._stats),
            rejected_reasons=dict(self._rejected_reasons),
        )

    def _advance(self, cutoff: int) -> None:
        while self._candle_i < len(self._candles):
            candle = self._candles[self._candle_i]
            if candle.close_time > cutoff:
                break
            index = self._candle_i
            decision = self._provider.decide(
                candle_index=index,
                decision_ts=candle.close_time,
                reference_price=candle.close,
                atr_value=self._atr[index],
                context=ContextSnapshot(
                    decision_ts=candle.close_time,
                    h1=self._context_at(self._h1_keys, self._ctx_1h, candle.close_time),
                    h4=self._context_at(self._h4_keys, self._ctx_4h, candle.close_time),
                ),
            )
            if decision is not None:
                self._queue.append(decision)
                self._stats["decisions_total"] += 1
            self._candle_i += 1

    @staticmethod
    def _context_at(
        keys: Sequence[int], rows: Sequence[CandleRow], decision_ts: int
    ) -> CandleRow | None:
        position = bisect.bisect_right(keys, decision_ts) - 1
        if position < 0:
            return None
        return rows[position]

    def _fill_pending_exit(self, trade: ReplayTrade, index: int) -> None:
        if self._pending is None:
            return
        position = self._position
        if position is None:
            raise ReplayError("exit pendiente sin posición (invariante rota)")
        pending = self._pending
        self._pending = None
        self._finish(
            position,
            pending,
            fill_ts=trade.ts,
            fill_trade_index=index,
            fill_trade_price=trade.price,
        )

    def _fill_pending_edge(self) -> None:
        pending = self._pending
        position = self._position
        if pending is None or position is None:
            raise ReplayError("exit pendiente sin posición (invariante rota)")
        if pending.trigger_trade_index is None:
            raise ReplayError("exit de riesgo sin índice de trade")
        self._pending = None
        self._finish(
            position,
            pending,
            fill_ts=pending.trigger_ts,
            fill_trade_index=pending.trigger_trade_index,
            fill_trade_price=pending.trigger_price,
        )

    def _drain_decisions(self, trade: ReplayTrade, index: int) -> None:
        while self._queue:
            decision = self._queue.popleft()
            if decision.action == "buy":
                atr_value = decision.atr
                if self._position is not None or atr_value is None:
                    self._stats["decisions_dropped"] += 1
                    continue
                verdict: RiskVerdict | None = None
                if self._dynamic:
                    # Orden M9-B: RiskEngine se evalúa en el PRIMER TRADE
                    # elegible, inmediatamente antes de abrir (nunca en el
                    # cierre de la vela) con el estado real del portfolio.
                    verdict = self._evaluate_risk(decision, trade)
                    if not verdict.approved:
                        self._stats["decisions_rejected"] += 1
                        self._rejected_reasons[verdict.reason] = (
                            self._rejected_reasons.get(verdict.reason, 0) + 1
                        )
                        continue
                self._open_position(decision, atr_value, trade, index, verdict)
                self._stats["decisions_filled"] += 1
            elif decision.action == "sell":
                position = self._position
                if position is None:
                    self._stats["decisions_dropped"] += 1
                    continue
                self._update_path(position, trade.price)
                self._finish(
                    position,
                    _PendingExit(
                        reason="strategy_exit",
                        trigger_ts=decision.signal_ts,
                        trigger_trade_index=None,
                        trigger_price=trade.price,
                        reference_price=decision.reference_price,
                    ),
                    fill_ts=trade.ts,
                    fill_trade_index=index,
                    fill_trade_price=trade.price,
                )
                self._stats["decisions_filled"] += 1
            else:
                raise ReplayError(f"acción desconocida: {decision.action!r}")

    def _roll_day(self, ts_ms: int) -> None:
        """Rueda el día UTC del pnl diario (determinista, sin wall-clock)."""
        day = ts_ms // DAY_MS
        if self._day is None:
            self._day = day
        elif day != self._day:
            self._day = day
            self._realized_today = 0.0

    def _evaluate_risk(self, decision: Decision, trade: ReplayTrade) -> RiskVerdict:
        """Evalúa RiskEngine al fill attempt con price=reference_price y atr=decisión."""
        self._roll_day(trade.ts)
        proposal = TradeProposal(
            action=Action.BUY,
            intensity=self._scenario.intensity,
            price=decision.reference_price,
            atr=decision.atr,
            timestamp_ms=decision.signal_ts,
        )
        state = PortfolioRiskState(
            open_positions=0,
            realized_pnl_today=self._realized_today,
            peak_equity=self._peak_equity,
            equity=self._capital + self._realized_total,
            kill_switch=self._risk_kill,
        )
        return self._risk_engine.evaluate(proposal, state)

    def _open_position(
        self,
        decision: Decision,
        atr_value: float,
        trade: ReplayTrade,
        index: int,
        verdict: RiskVerdict | None = None,
    ) -> None:
        scenario = self._scenario
        entry_execution = trade.price * (1.0 + scenario.slippage_bps / 10_000.0)
        if verdict is not None:
            # M9-B: stop/target y quantity provienen del veredicto RiskEngine,
            # calculados sobre reference_price (close confirmado), no sobre
            # entry_execution_price.
            if verdict.size is None or verdict.stop_loss is None or verdict.take_profit is None:
                raise ReplayError("RiskEngine aprobado sin size/stop/target (FAIL CLOSED)")
            quantity = verdict.size.quantity
            stop = verdict.stop_loss
            target = verdict.take_profit
        else:
            quantity = scenario.quantity
            stop = initial_stop(entry_price=entry_execution, atr=atr_value, config=scenario.risk)
            target = take_profit(entry_price=entry_execution, stop_loss=stop, config=scenario.risk)
        self._position = _Position(
            quantity=quantity,
            entry_signal_ts=decision.signal_ts,
            entry_trigger_ts=decision.signal_ts,
            entry_fill_ts=trade.ts,
            entry_reference_price=decision.reference_price,
            entry_execution_price=entry_execution,
            entry_trade_price=trade.price,
            entry_candle_index=decision.candle_index,
            entry_fill_trade_index=index,
            atr=atr_value,
            initial_stop=stop,
            initial_target=target,
            trailing=stop,
            highest=entry_execution,
            lowest=entry_execution,
        )

    @staticmethod
    def _update_path(position: _Position, price: float) -> None:
        position.highest = max(position.highest, price)
        position.lowest = min(position.lowest, price)

    def _risk_eval(self, trade: ReplayTrade, index: int) -> None:
        position = self._position
        if position is None or trade.ts <= position.entry_fill_ts:
            return
        self._update_path(position, trade.price)
        protective = max(position.initial_stop, position.trailing)
        if trade.price <= protective:
            reason = "trailing_stop" if protective > position.entry_execution_price else "stop_loss"
            self._pending = _PendingExit(
                reason=reason,
                trigger_ts=trade.ts,
                trigger_trade_index=index,
                trigger_price=trade.price,
                reference_price=protective,
            )
            return
        if trade.price >= position.initial_target:
            self._pending = _PendingExit(
                reason="take_profit",
                trigger_ts=trade.ts,
                trigger_trade_index=index,
                trigger_price=trade.price,
                reference_price=position.initial_target,
            )
            return
        new_stop = update_trailing(
            current_stop=position.trailing,
            highest_price=position.highest,
            atr=position.atr,
            config=self._scenario.risk,
        )
        if new_stop > position.trailing:
            position.trailing = new_stop
            position.trailing_updates += 1

    def _finish(
        self,
        position: _Position,
        pending: _PendingExit,
        *,
        fill_ts: int,
        fill_trade_index: int | None,
        fill_trade_price: float,
    ) -> None:
        scenario = self._scenario
        slip = scenario.slippage_bps / 10_000.0
        exit_execution = fill_trade_price * (1.0 - slip)
        gross = (fill_trade_price - position.entry_trade_price) * position.quantity
        slippage = slip * (position.entry_trade_price + fill_trade_price) * position.quantity
        fees = (
            scenario.fee_rate
            * (position.entry_execution_price + exit_execution)
            * position.quantity
        )
        net = gross - slippage - fees
        record: dict[str, object] = {
            "record_type": "trade",
            "entry_signal_timestamp": position.entry_signal_ts,
            "entry_trigger_timestamp": position.entry_trigger_ts,
            "entry_fill_timestamp": position.entry_fill_ts,
            "entry_reference_price": position.entry_reference_price,
            "entry_execution_price": position.entry_execution_price,
            "entry_trade_price": position.entry_trade_price,
            "entry_candle_index": position.entry_candle_index,
            "entry_fill_trade_index": position.entry_fill_trade_index,
            "atr_at_entry": position.atr,
            "initial_stop": position.initial_stop,
            "initial_target": position.initial_target,
            "mfe": max(position.highest - position.entry_execution_price, 0.0),
            "mae": max(position.entry_execution_price - position.lowest, 0.0),
            "highest_price": position.highest,
            "exit_trigger_timestamp": pending.trigger_ts,
            "exit_fill_timestamp": fill_ts,
            "exit_trigger_trade_index": pending.trigger_trade_index,
            "exit_fill_trade_index": fill_trade_index,
            "exit_reason": pending.reason,
            "exit_reference_price": pending.reference_price,
            "exit_execution_price": exit_execution,
            "exit_trade_price": fill_trade_price,
            "quantity": position.quantity,
            "fees": fees,
            "slippage": slippage,
            "gross_pnl": gross,
            "net_pnl": net,
            "holding_ms": fill_ts - position.entry_fill_ts,
            "trailing_updates": position.trailing_updates,
            "strategy_version": scenario.strategy_version,
            "risk_version": scenario.risk.version,
            "execution_model_version": EXECUTION_MODEL_VERSION,
            "dataset_id": self._dataset_id,
            "dataset_sha": self._dataset_sha,
        }
        self._records.append(record)
        self._stats["closed_trades"] += 1
        if self._dynamic:
            self._roll_day(fill_ts)
            self._realized_total += net
            self._realized_today += net
            equity = self._capital + self._realized_total
            if equity > self._peak_equity:
                self._peak_equity = equity
        self._position = None
        self._pending = None


def replay_engine(
    candles_15m: Sequence[CandleRow],
    ctx_1h: Sequence[CandleRow],
    ctx_4h: Sequence[CandleRow],
    trades: Iterable[ReplayTrade],
    scenario: ReplayScenario,
    provider: DecisionProvider,
    *,
    dataset_id: str,
    dataset_sha: str,
) -> ReplayResult:
    """Replay determinista de dos relojes sobre un dataset validado."""
    return _Engine(
        candles_15m,
        ctx_1h,
        ctx_4h,
        trades,
        scenario,
        provider,
        dataset_id=dataset_id,
        dataset_sha=dataset_sha,
    ).run()


# ----------------------------------------------------------------- ledger


def _json_line(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def ledger_payload(
    result: ReplayResult,
    *,
    dataset_id: str,
    dataset_sha: str,
    symbol: str,
    dates: Sequence[date],
    ordering_fidelity: str,
    scenario: ReplayScenario,
) -> bytes:
    """JSONL determinista: run_meta + registros (sin wall-clock)."""
    meta: dict[str, object] = {
        "record_type": "run_meta",
        "ledger_version": LEDGER_VERSION,
        "dataset_id": dataset_id,
        "dataset_sha": dataset_sha,
        "symbol": symbol,
        "dates": [d.isoformat() for d in dates],
        "ordering_fidelity": ordering_fidelity,
        "execution_model": EXECUTION_MODEL,
        "execution_model_version": EXECUTION_MODEL_VERSION,
        "strategy_version": scenario.strategy_version,
        "risk_version": scenario.risk.version,
        "scenario": scenario.scenario_id,
        "candle_visibility": CANDLE_VISIBILITY,
        "fill_rule": FILL_RULE,
        "pnl_basis": PNL_BASIS,
        "exit_reason_catalog": list(EXIT_REASONS),
        "decisions_total": result.stats["decisions_total"],
        "decisions_filled": result.stats["decisions_filled"],
        "decisions_dropped": result.stats["decisions_dropped"],
        "decisions_unfilled": result.stats["decisions_unfilled"],
        "closed_trades": result.stats["closed_trades"],
    }
    if scenario.sizing_mode != "fixed":
        # Auditoría M9-B solo en modo dinámico: el ledger legacy (fixed) debe
        # permanecer byte-idéntico al UAT M7.
        meta["sizing_mode"] = scenario.sizing_mode
        meta["intensity"] = scenario.intensity
        meta["decisions_rejected"] = result.stats.get("decisions_rejected", 0)
        meta["rejected_reasons"] = dict(sorted(result.rejected_reasons.items()))
    lines = [_json_line(meta)]
    lines.extend(_json_line(record) for record in result.records)
    return ("\n".join(lines) + "\n").encode("utf-8")


def write_ledger(path: Path, payload: bytes) -> str:
    """Escritura única idempotente: created | skipped | FAIL CLOSED."""
    if path.exists():
        if path.read_bytes() == payload:
            return "skipped"
        raise LedgerConflictError(f"ledger existente con contenido distinto: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(payload)
    if part.read_bytes() != payload:
        part.unlink(missing_ok=True)
        raise ReplayError(f"round-trip del ledger fallido: {path}")
    os.replace(part, path)
    return "created"
