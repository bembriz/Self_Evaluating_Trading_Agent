"""Phase 24 Medallion refresh orchestrator.

This module plans and runs an incremental daily refresh over the existing Medallion
layers. It deliberately does not install systemd units, enforce capacity quotas, or
promote future data to Gold/research. Those are separate Phase 24 deliverables.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from infrastructure.medallion import bronze, candles, silver
from infrastructure.medallion.bronze import DEFAULT_BASE_URL
from infrastructure.medallion.capacity_guards import (
    CapacityGuardConfig,
    CapacityGuardError,
    CapacityProbe,
    run_capacity_preflight,
)
from infrastructure.medallion.split_guard import (
    DEFAULT_INGEST_SCOPE,
    DEVELOPMENT_FIRST_DAY,
    DEVELOPMENT_LAST_DAY,
    FINAL_HOLDOUT_FIRST_DAY,
    FINAL_HOLDOUT_LAST_DAY,
    WALK_FORWARD_FIRST_DAY,
    IngestClass,
    IngestScope,
    classify_ingest_day,
)

__all__ = [
    "AccessBlockedError",
    "AccessClass",
    "CapacityGuardError",
    "DefaultRefreshOperations",
    "Layer",
    "RefreshConfig",
    "RefreshExecutionError",
    "RefreshPlan",
    "RefreshResult",
    "RefreshStep",
    "classify_day",
    "plan_refresh",
    "run_refresh",
    "write_status_atomic",
]


class AccessClass(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"
    WALK_FORWARD = "WALK_FORWARD"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"
    FUTURE_COLLECTION = "FUTURE_COLLECTION"


class Layer(StrEnum):
    BRONZE = "bronze"
    SILVER_TRADES = "silver_trades"
    SILVER_CANDLES = "silver_candles"


class AccessBlockedError(RuntimeError):
    """Automatic refresh attempted to touch a blocked evaluation split."""


class RefreshExecutionError(RuntimeError):
    """A refresh step failed after earlier steps may have completed."""


class RefreshOperations(Protocol):
    def download_bronze(self, day: date) -> str: ...

    def transform_silver(self, day: date) -> str: ...

    def transform_candles(self, day: date) -> str: ...


@dataclass(frozen=True)
class RefreshConfig:
    symbol: str
    bronze_dir: Path
    silver_dir: Path
    candles_dir: Path
    gold_dir: Path
    status_path: Path
    start_day: date
    target_day: date
    bronze_base_url: str = DEFAULT_BASE_URL
    capacity_guard: CapacityGuardConfig | None = None
    ingest_scope: IngestScope = DEFAULT_INGEST_SCOPE


@dataclass(frozen=True)
class RefreshStep:
    layer: Layer
    day: date
    access: AccessClass

    @property
    def key(self) -> str:
        return f"{self.layer.value}:{self.day.isoformat()}"


@dataclass(frozen=True)
class RefreshPlan:
    steps: list[RefreshStep]
    blocked_days: list[date]
    gold_blocked_days: list[date]
    unassigned_research_reads: int = 0


@dataclass(frozen=True)
class RefreshResult:
    result: str
    dry_run: bool
    planned_steps: int
    executed_steps: int
    completed_steps: list[str]
    blocked_days: list[date] = field(default_factory=list)
    gold_blocked_days: list[date] = field(default_factory=list)
    unassigned_research_reads: int = 0


@dataclass(frozen=True)
class DefaultRefreshOperations:
    """Thin adapter over existing Medallion layer functions."""

    config: RefreshConfig

    def _scope_for(self, day: date) -> IngestScope:
        # Solo los días FUTURE_COLLECTION pueden usar el scope ampliado del
        # orquestador; DEVELOPMENT siempre permanece en el scope por defecto y
        # WF/HOLDOUT los bloquea split_guard de forma incondicional.
        if classify_ingest_day(day) is IngestClass.FUTURE_COLLECTION:
            return self.config.ingest_scope
        return DEFAULT_INGEST_SCOPE

    def download_bronze(self, day: date) -> str:
        result = bronze.download_day(
            self.config.bronze_dir,
            self.config.symbol,
            day,
            base_url=self.config.bronze_base_url,
            scope=self._scope_for(day),
        )
        return result.status

    def transform_silver(self, day: date) -> str:
        result = silver.transform_day(
            self.config.bronze_dir,
            self.config.silver_dir,
            self.config.symbol,
            day,
            scope=self._scope_for(day),
        )
        return result.status

    def transform_candles(self, day: date) -> str:
        results = candles.transform_day(
            self.config.silver_dir,
            self.config.candles_dir,
            self.config.symbol,
            day,
            scope=self._scope_for(day),
        )
        if not results:
            return "skipped"
        if all(result.status == "skipped" for result in results):
            return "skipped"
        return "transformed"


def classify_day(day: date) -> AccessClass:
    if DEVELOPMENT_FIRST_DAY <= day <= DEVELOPMENT_LAST_DAY:
        return AccessClass.DEVELOPMENT
    if WALK_FORWARD_FIRST_DAY <= day < FINAL_HOLDOUT_FIRST_DAY:
        return AccessClass.WALK_FORWARD
    if FINAL_HOLDOUT_FIRST_DAY <= day <= FINAL_HOLDOUT_LAST_DAY:
        return AccessClass.FINAL_HOLDOUT
    return AccessClass.FUTURE_COLLECTION


def _days(start: date, target: date) -> Iterable[date]:
    if target < start:
        return ()
    count = (target - start).days + 1
    return (start + timedelta(days=offset) for offset in range(count))


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RefreshExecutionError(f"status/manifest JSON ilegible: {path}") from exc
    if not isinstance(loaded, dict):
        raise RefreshExecutionError(f"JSON no es un objeto: {path}")
    return loaded


def _manifest_filenames(root: Path) -> set[str]:
    manifest = _load_json(root / "manifest.json")
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        raise RefreshExecutionError(f"manifest files inválido: {root / 'manifest.json'}")
    return {name for name in files if isinstance(name, str)}


def _bronze_or_silver_filename(symbol: str, day: date) -> str:
    return f"{symbol}_{day.isoformat()}.csv.gz"


def _has_candles_for_day(filenames: set[str], symbol: str, day: date) -> bool:
    prefix = f"{symbol}_{day.isoformat()}_"
    return any(name.startswith(prefix) and name.endswith(".csv.gz") for name in filenames)


def _load_completed_steps(status_path: Path) -> set[str]:
    payload = _load_json(status_path)
    raw = payload.get("completed_steps", [])
    if not isinstance(raw, list):
        raise RefreshExecutionError(f"completed_steps inválido en {status_path}")
    return {item for item in raw if isinstance(item, str)}


def plan_refresh(config: RefreshConfig) -> RefreshPlan:
    if config.bronze_base_url != DEFAULT_BASE_URL:
        raise RefreshExecutionError(
            f"bronze_base_url must be exact approved source {DEFAULT_BASE_URL!r}"
        )
    completed = _load_completed_steps(config.status_path)
    bronze_files = _manifest_filenames(config.bronze_dir)
    silver_files = _manifest_filenames(config.silver_dir)
    candle_files = _manifest_filenames(config.candles_dir)

    steps: list[RefreshStep] = []
    blocked_days: list[date] = []
    gold_blocked_days: list[date] = []

    for day in _days(config.start_day, config.target_day):
        access = classify_day(day)
        if access in {AccessClass.WALK_FORWARD, AccessClass.FINAL_HOLDOUT}:
            blocked_days.append(day)
            continue
        if access is AccessClass.FUTURE_COLLECTION:
            gold_blocked_days.append(day)

        filename = _bronze_or_silver_filename(config.symbol, day)
        candidates = [
            (Layer.BRONZE, filename not in bronze_files),
            (Layer.SILVER_TRADES, filename not in silver_files),
            (Layer.SILVER_CANDLES, not _has_candles_for_day(candle_files, config.symbol, day)),
        ]
        for layer, missing in candidates:
            step = RefreshStep(layer=layer, day=day, access=access)
            if missing and step.key not in completed:
                steps.append(step)

    return RefreshPlan(
        steps=steps,
        blocked_days=blocked_days,
        gold_blocked_days=gold_blocked_days,
        unassigned_research_reads=0,
    )


def _status_payload(
    config: RefreshConfig,
    result: str,
    plan: RefreshPlan,
    completed_steps: set[str],
    *,
    dry_run: bool,
    executed_steps: int,
    failed_step: RefreshStep | None = None,
) -> dict[str, object]:
    layer_order = {
        Layer.BRONZE.value: 0,
        Layer.SILVER_TRADES.value: 1,
        Layer.SILVER_CANDLES.value: 2,
    }

    def completed_sort_key(key: str) -> tuple[str, int]:
        layer, _, day = key.partition(":")
        return day, layer_order.get(layer, 99)

    payload: dict[str, object] = {
        "result": result,
        "dry_run": dry_run,
        "symbol": config.symbol,
        "start_day": config.start_day.isoformat(),
        "target_day": config.target_day.isoformat(),
        "planned_steps": len(plan.steps),
        "executed_steps": executed_steps,
        "completed_steps": sorted(completed_steps, key=completed_sort_key),
        "blocked_days": [day.isoformat() for day in plan.blocked_days],
        "gold_blocked_days": [day.isoformat() for day in plan.gold_blocked_days],
        "unassigned_research_reads": plan.unassigned_research_reads,
    }
    if failed_step is not None:
        payload["failed_step"] = failed_step.key
    return payload


def write_status_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(part, path)


def _result_from_payload(payload: dict[str, object], plan: RefreshPlan) -> RefreshResult:
    def str_list(key: str) -> list[str]:
        value = payload.get(key, [])
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    def int_value(key: str, default: int) -> int:
        value = payload.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            return default
        return value

    completed = str_list("completed_steps")
    blocked = [date.fromisoformat(item) for item in str_list("blocked_days")]
    gold_blocked = [date.fromisoformat(item) for item in str_list("gold_blocked_days")]
    return RefreshResult(
        result=str(payload.get("result", "FAILED_GUARD")),
        dry_run=bool(payload.get("dry_run", False)),
        planned_steps=int_value("planned_steps", len(plan.steps)),
        executed_steps=int_value("executed_steps", 0),
        completed_steps=completed,
        blocked_days=blocked,
        gold_blocked_days=gold_blocked,
        unassigned_research_reads=int_value("unassigned_research_reads", 0),
    )


def run_refresh(
    config: RefreshConfig,
    *,
    operations: RefreshOperations | None = None,
    dry_run: bool = False,
    capacity_probe: CapacityProbe | None = None,
) -> RefreshResult:
    plan = plan_refresh(config)
    if plan.blocked_days:
        payload = _status_payload(
            config,
            "ACCESS_BLOCKED",
            plan,
            _load_completed_steps(config.status_path),
            dry_run=dry_run,
            executed_steps=0,
        )
        if not dry_run:
            write_status_atomic(config.status_path, payload)
        raise AccessBlockedError(
            "automatic refresh blocked for frozen evaluation split days: "
            + ", ".join(day.isoformat() for day in plan.blocked_days)
        )

    completed = _load_completed_steps(config.status_path)
    if config.capacity_guard is not None:
        try:
            run_capacity_preflight(
                config.capacity_guard,
                probe=capacity_probe,
                allow_purge=not dry_run,
            )
        except CapacityGuardError:
            if not dry_run:
                write_status_atomic(
                    config.status_path,
                    _status_payload(
                        config,
                        "FAIL_GUARD",
                        plan,
                        completed,
                        dry_run=False,
                        executed_steps=0,
                    ),
                )
            raise

    if dry_run:
        return RefreshResult(
            result="OK_NOOP" if not plan.steps else "OK",
            dry_run=True,
            planned_steps=len(plan.steps),
            executed_steps=0,
            completed_steps=sorted(completed),
            blocked_days=plan.blocked_days,
            gold_blocked_days=plan.gold_blocked_days,
            unassigned_research_reads=plan.unassigned_research_reads,
        )

    ops = operations if operations is not None else DefaultRefreshOperations(config)
    executed = 0
    for step in plan.steps:
        if step.key in completed:
            continue
        try:
            if step.layer is Layer.BRONZE:
                ops.download_bronze(step.day)
            elif step.layer is Layer.SILVER_TRADES:
                ops.transform_silver(step.day)
            else:
                ops.transform_candles(step.day)
        except Exception as exc:
            payload = _status_payload(
                config,
                "FAILED_PARTIAL",
                plan,
                completed,
                dry_run=False,
                executed_steps=executed,
                failed_step=step,
            )
            write_status_atomic(config.status_path, payload)
            raise RefreshExecutionError(f"refresh failed at {step.key}: {exc}") from exc
        completed.add(step.key)
        executed += 1
        write_status_atomic(
            config.status_path,
            _status_payload(
                config,
                "RUNNING",
                plan,
                completed,
                dry_run=False,
                executed_steps=executed,
            ),
        )

    final_result = "OK" if executed else "OK_NOOP"
    payload = _status_payload(
        config,
        final_result,
        plan,
        completed,
        dry_run=False,
        executed_steps=executed,
    )
    write_status_atomic(config.status_path, payload)
    return _result_from_payload(payload, plan)
