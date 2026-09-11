"""ExperimentSpec/Run e identidad determinista (Fase 17A, Strategy Lab).

Contrato canónico (CANONICAL_JSON v1):
- Representación única: JSON UTF-8, claves ordenadas, sin espacios
  (`separators=(",", ":")`, `sort_keys=True`, `ensure_ascii=True`).
- Tipos aceptados: None, bool, int, float FINITO, str, list, tuple (= lista),
  Mapping con claves str (normalizado a dict plano).
- Rechazados con excepción (fail closed, sin coerción silenciosa):
  float NaN/±Infinity (ValueError); Decimal, datetime, Enum, Path, bytes,
  set/frozenset, claves no-str, cualquier otro objeto (TypeError).
- Decisiones documentadas: tuple se serializa como lista JSON (orden conservado,
  sin ambigüedad); Enum —incluidos los basados en str— se rechaza (usar `.value`
  explícito en la frontera); Decimal/datetime/Path/bytes exigen conversión
  explícita en la frontera; `0.0` vs `-0.0` y `1` vs `1.0` son valores distintos
  (repr JSON exacto, sin normalización silenciosa).

ExperimentSpecId = sha256 de la serialización canónica de SOLO los inputs
semánticos. Provenance (created_at, run_id, hashes de resultado,
application_git_sha) vive en ExperimentRun y NUNCA altera el SpecId
(clarificación HUMAN_GATE: un cambio docs-only preserva la identidad
experimental). `kernel_identity` es un placeholder opaco tipado en 17A;
17B definirá su contenido (sin application_git_sha).

Inmutabilidad profunda: tras `__post_init__`, todas las secciones del Spec
quedan congeladas recursivamente (dict → MappingProxyType, list → tuple),
de modo que ni el holder ni el caller original pueden mutarlas. La
serialización canónica acepta esos tipos congelados y produce exactamente
el mismo JSON que sus equivalentes mutables.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from types import MappingProxyType
from typing import Any, cast

ALLOWED_EXECUTION_MODELS = frozenset({"fast-research", "runtime-parity"})
ALLOWED_RUN_STATUS = ("ok", "failed")

_HEX64_RE = re.compile(r"[0-9a-f]{64}")


def _normalize(value: object) -> object:
    """Normaliza a tipos JSON canónicos; rechaza lo ambiguo."""
    # Enum PRIMERO: StrEnum es str e IntEnum es int; aceptar str/int antes
    # dejaría pasar Enums por el fail-closed. Sin conversión a .value.
    if isinstance(value, Enum):
        raise TypeError(f"Enum values must use .value explicitly: {value!r}")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, datetime):
        raise TypeError(f"datetime must be ISO-8601 str at the boundary: {value!r}")
    if isinstance(value, Decimal):
        raise TypeError(f"Decimal must be converted explicitly: {value!r}")
    if isinstance(value, PurePath):
        raise TypeError(f"Path must be str at the boundary: {value!r}")
    if isinstance(value, bytes):
        raise TypeError("bytes must be encoded explicitly (e.g. hex)")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float not canonical: {value!r}")
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        raise TypeError(f"unordered set not canonical: {value!r}")
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"non-string mapping key not canonical: {key!r}")
            normalized[key] = _normalize(item)
        return normalized
    raise TypeError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Serialización canónica única del contrato CANONICAL_JSON v1."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_bytes(value: object) -> bytes:
    """Bytes UTF-8 de la representación canónica."""
    return canonical_json(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Hex digest SHA-256."""
    return hashlib.sha256(data).hexdigest()


def _freeze(value: object) -> object:
    """Congela recursivamente: Mapping → MappingProxyType, list → tuple."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _section(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping, got {type(value).__name__}")
    return cast(Mapping[str, Any], _freeze(_normalize(value)))


@dataclass(frozen=True)
class ExperimentSpec:
    """Definición inmutable de un experimento (solo inputs semánticos)."""

    dataset: Mapping[str, Any]
    strategy: Mapping[str, Any]
    risk: Mapping[str, Any]
    execution: Mapping[str, Any]
    fees: Mapping[str, Any]
    slippage: Mapping[str, Any]
    timing_model: str
    holdout_protocol: str
    kernel_identity: Mapping[str, Any]
    seed: str | None = None
    walk_forward: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset", _section(self.dataset, "dataset"))
        object.__setattr__(self, "strategy", _section(self.strategy, "strategy"))
        object.__setattr__(self, "risk", _section(self.risk, "risk"))
        object.__setattr__(self, "execution", _section(self.execution, "execution"))
        object.__setattr__(self, "fees", _section(self.fees, "fees"))
        object.__setattr__(self, "slippage", _section(self.slippage, "slippage"))
        object.__setattr__(
            self, "kernel_identity", _section(self.kernel_identity, "kernel_identity")
        )
        if self.seed is not None and not isinstance(self.seed, str):
            raise TypeError(f"seed must be str | None, got {type(self.seed).__name__}")
        if self.walk_forward is not None:
            object.__setattr__(self, "walk_forward", _section(self.walk_forward, "walk_forward"))
        for name in ("timing_model", "holdout_protocol"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty str")
        model = self.execution.get("model")
        if model not in ALLOWED_EXECUTION_MODELS:
            raise ValueError(f"unknown execution model: {model!r}")
        version = self.execution.get("version")
        if not isinstance(version, str) or not version:
            raise ValueError("execution.version must be a non-empty str")


def _spec_to_dict(spec: ExperimentSpec) -> dict[str, Any]:
    return {
        "dataset": spec.dataset,
        "strategy": spec.strategy,
        "risk": spec.risk,
        "execution": spec.execution,
        "fees": spec.fees,
        "slippage": spec.slippage,
        "timing_model": spec.timing_model,
        "seed": spec.seed,
        "walk_forward": spec.walk_forward,
        "holdout_protocol": spec.holdout_protocol,
        "kernel_identity": spec.kernel_identity,
    }


def spec_id(spec: ExperimentSpec) -> str:
    """ExperimentSpecId determinista: sha256 del canónico de solo-inputs."""
    return sha256_hex(canonical_bytes(_spec_to_dict(spec)))


def event_trace_hash(trace: object) -> str:
    """Hash determinista de una traza de eventos."""
    return sha256_hex(canonical_bytes(trace))


def metrics_hash(metrics: object) -> str:
    """Hash determinista de un mapping de métricas."""
    return sha256_hex(canonical_bytes(metrics))


def _check_hash(name: str, value: str | None) -> None:
    if value is None:
        return
    if _HEX64_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be SHA-256 hex or None, got {value!r}")


@dataclass(frozen=True)
class ExperimentRun:
    """Una ejecución (provenance + outputs) referenciando un SpecId."""

    experiment_spec_id: str
    run_id: str
    created_at: str
    application_git_sha: str
    status: str
    event_trace_hash: str | None
    metrics_hash: str | None

    def __post_init__(self) -> None:
        if _HEX64_RE.fullmatch(self.experiment_spec_id) is None:
            raise ValueError(
                f"experiment_spec_id must be SHA-256 hex, got {self.experiment_spec_id!r}"
            )
        if not self.run_id.strip():
            raise ValueError("run_id must be a non-empty str")
        try:
            datetime.fromisoformat(self.created_at)
        except ValueError:
            raise ValueError(f"created_at must be ISO-8601, got {self.created_at!r}") from None
        if not self.application_git_sha:
            raise ValueError("application_git_sha must be a non-empty str")
        if self.status not in ALLOWED_RUN_STATUS:
            raise ValueError(f"unknown status: {self.status!r}")
        _check_hash("event_trace_hash", self.event_trace_hash)
        _check_hash("metrics_hash", self.metrics_hash)
