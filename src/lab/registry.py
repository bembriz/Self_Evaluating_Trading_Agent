"""ExperimentRegistry filesystem mínimo (Fase 17E).

Estructura::

    <root>/<spec_id>/spec.json
    <root>/<spec_id>/runs/<run_id>.json

Inmutabilidad fail closed: re-registrar el mismo contenido exacto es
idempotente; contenido diferente bajo el mismo SpecId/RunId se rechaza.
Sin base de datos, sin ORM, sin promotion logic.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lab.experiment_spec import ExperimentRun, ExperimentSpec, spec_id

_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class SpecConflictError(ValueError):
    """Contenido diferente bajo un SpecId ya registrado."""


class RunConflictError(ValueError):
    """Contenido diferente bajo un RunId ya persistido."""


def _to_plain(value: object) -> Any:
    """Mapping/tuple congelados → dict/list planos para JSON."""
    if isinstance(value, Mapping):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError(f"run_id inválido: {run_id!r}")


@dataclass(frozen=True, slots=True)
class ReproducibilityReport:
    """Resultado conceptual de comparar dos runs del mismo experimento."""

    same_spec_id: bool
    event_trace_hash_match: bool
    metrics_hash_match: bool
    reproducible: bool


def compare_runs(run_a: ExperimentRun, run_b: ExperimentRun) -> ReproducibilityReport:
    """Compara dos runs: mismo spec + hashes iguales (existentes) = reproducible."""
    same_spec = run_a.experiment_spec_id == run_b.experiment_spec_id
    trace_match = (
        run_a.event_trace_hash is not None and run_a.event_trace_hash == run_b.event_trace_hash
    )
    metrics_match = run_a.metrics_hash is not None and run_a.metrics_hash == run_b.metrics_hash
    return ReproducibilityReport(
        same_spec_id=same_spec,
        event_trace_hash_match=trace_match,
        metrics_hash_match=metrics_match,
        reproducible=same_spec and trace_match and metrics_match,
    )


class ExperimentRegistry:
    """Registro filesystem de specs y runs. Determinista y fail closed."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _spec_path(self, wanted_spec_id: str) -> Path:
        if _HEX64_RE.fullmatch(wanted_spec_id) is None:
            raise ValueError(f"spec_id inválido: {wanted_spec_id!r}")
        return self._root / wanted_spec_id / "spec.json"

    def _run_path(self, wanted_spec_id: str, run_id: str) -> Path:
        _check_run_id(run_id)
        return self._root / wanted_spec_id / "runs" / f"{run_id}.json"

    def register_spec(self, spec: ExperimentSpec) -> str:
        """Registra el spec; idempotente ante contenido idéntico."""
        wanted = spec_id(spec)
        path = self._spec_path(wanted)
        payload = {"spec_id": wanted, "spec": _to_plain(_spec_to_mapping(spec))}
        if path.is_file():
            if _read_json(path) != payload:
                raise SpecConflictError(f"contenido conflictivo bajo spec {wanted}")
            return wanted
        _write_json(path, payload)
        return wanted

    def load_spec(self, wanted_spec_id: str) -> ExperimentSpec:
        """Carga y re-verifica que el contenido corresponde al SpecId."""
        path = self._spec_path(wanted_spec_id)
        if not path.is_file():
            raise FileNotFoundError(f"spec desconocido: {wanted_spec_id}")
        payload = _read_json(path)
        spec = ExperimentSpec(**payload["spec"])
        if spec_id(spec) != wanted_spec_id:
            raise SpecConflictError(f"spec.json manipulado bajo {wanted_spec_id}")
        return spec

    def register_run(self, run: ExperimentRun) -> Path:
        """Persiste el run; exige spec registrado; idempotente ante igualdad."""
        if not self._spec_path(run.experiment_spec_id).is_file():
            raise ValueError(f"spec no registrado: {run.experiment_spec_id}")
        path = self._run_path(run.experiment_spec_id, run.run_id)
        payload = {"run_id": run.run_id, "run": _to_plain(_run_to_mapping(run))}
        if path.is_file():
            if _read_json(path) != payload:
                raise RunConflictError(f"contenido conflictivo bajo run {run.run_id}")
            return path
        _write_json(path, payload)
        return path

    def load_run(self, wanted_spec_id: str, run_id: str) -> ExperimentRun:
        """Carga un run persistido."""
        path = self._run_path(wanted_spec_id, run_id)
        if not path.is_file():
            raise FileNotFoundError(f"run desconocido: {run_id}")
        payload = _read_json(path)
        run = ExperimentRun(**payload["run"])
        if run.experiment_spec_id != wanted_spec_id or run.run_id != run_id:
            raise RunConflictError(f"run manipulado: {run_id}")
        return run

    def list_runs(self, wanted_spec_id: str) -> tuple[str, ...]:
        """RunIds persistidos bajo un spec, ordenados (auditoría)."""
        runs_dir = self._root / wanted_spec_id / "runs"
        if not runs_dir.is_dir():
            return ()
        return tuple(sorted(path.stem for path in runs_dir.glob("*.json")))


def _spec_to_mapping(spec: ExperimentSpec) -> dict[str, Any]:
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


def _run_to_mapping(run: ExperimentRun) -> dict[str, Any]:
    return {
        "experiment_spec_id": run.experiment_spec_id,
        "run_id": run.run_id,
        "created_at": run.created_at,
        "application_git_sha": run.application_git_sha,
        "status": run.status,
        "event_trace_hash": run.event_trace_hash,
        "metrics_hash": run.metrics_hash,
    }
