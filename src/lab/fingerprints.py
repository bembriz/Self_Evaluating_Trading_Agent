"""Identidad de estrategia: ImplementationFingerprint vs StrategyArtifactIdentity.

Separación normativa (Fase 17B):
- ImplementationFingerprint: SOLO el bundle de implementación (fuentes
  declaradas + extras por kind). Sin id, versión, config, kernel ni app SHA.
- StrategyArtifactIdentity: id + versión + api + config normalizada +
  implementation_fingerprint. Sin kernel ni app SHA.

Toda serialización usa el contrato CANONICAL_JSON v1 de
`lab.experiment_spec` (sin segunda implementación). Las secciones de
config/prompts quedan congeladas en `__post_init__` (mismo criterio que 17A).
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, cast

from lab.experiment_spec import canonical_bytes, sha256_hex

STRATEGY_API_VERSION = 1
ALLOWED_STRATEGY_KINDS = frozenset({"deterministic", "ml", "llm-assisted"})


class SourceResolver(Protocol):
    """Resuelve contenido fuente por nombre de módulo (sin paths en hashes)."""

    def get_source(self, module_name: str) -> str: ...


class ImportlibSourceResolver:
    """Resolver real: fuente vía importlib/loader/inspect. Fail closed."""

    def get_source(self, module_name: str) -> str:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ValueError(f"unknown strategy module: {module_name}") from exc
        try:
            return inspect.getsource(module)
        except (OSError, TypeError) as exc:
            raise ValueError(f"no source available for module: {module_name}") from exc


class DictSourceResolver:
    """Doble de test: fuentes sintéticas en memoria."""

    def __init__(self, sources: Mapping[str, str]) -> None:
        self._sources = dict(sources)

    def get_source(self, module_name: str) -> str:
        try:
            return self._sources[module_name]
        except KeyError:
            raise ValueError(f"unknown strategy module: {module_name}") from None


def _freeze(value: object) -> object:
    """Congela recursivamente (mirror mínimo del criterio 17A)."""
    if isinstance(value, Mapping):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class StrategyDefinition:
    """Bundle declarado de una estrategia. `sources` sin duplicados ni orden."""

    strategy_id: str
    strategy_version: str
    strategy_api_version: int = STRATEGY_API_VERSION
    kind: str = "deterministic"
    normalized_config: Mapping[str, Any] = field(default_factory=dict)
    sources: tuple[str, ...] = ()
    prompts: Mapping[str, str] | None = None
    model_artifact: str | None = None
    feature_pipeline: str | None = None

    def __post_init__(self) -> None:
        for name in ("strategy_id", "strategy_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty str")
        if not isinstance(self.strategy_api_version, int) or self.strategy_api_version < 1:
            raise ValueError("strategy_api_version must be a positive int")
        if self.kind not in ALLOWED_STRATEGY_KINDS:
            raise ValueError(f"unknown strategy kind: {self.kind!r}")
        if not isinstance(self.sources, tuple):
            raise TypeError(f"sources must be tuple[str, ...], got {type(self.sources).__name__}")
        if not self.sources:
            raise ValueError("sources must declare at least one module")
        for item in self.sources:
            if not isinstance(item, str):
                raise TypeError(f"source entry must be str, got {type(item).__name__}")
            if not item:
                raise ValueError("source entry must be non-empty")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError(f"duplicate sources: {self.sources!r}")
        if not isinstance(self.normalized_config, Mapping):
            raise TypeError(
                f"normalized_config must be a mapping, got {type(self.normalized_config).__name__}"
            )
        object.__setattr__(self, "normalized_config", _freeze(self.normalized_config))
        if self.prompts is not None:
            object.__setattr__(self, "prompts", _freeze(self.prompts))
        if self.kind == "deterministic":
            for name in ("prompts", "model_artifact", "feature_pipeline"):
                if getattr(self, name) is not None:
                    raise ValueError(f"{name} must be None for deterministic kind")
        elif self.kind == "ml":
            if not isinstance(self.model_artifact, str) or not self.model_artifact:
                raise ValueError("ml kind requires non-empty model_artifact str")
            if self.prompts is not None:
                raise ValueError("prompts must be None for ml kind")
            pipeline = self.feature_pipeline
            if pipeline is not None and (not isinstance(pipeline, str) or not pipeline):
                raise ValueError("feature_pipeline must be str | None")
        else:  # llm-assisted (único valor restante permitido)
            prompts = self.prompts
            if not isinstance(prompts, Mapping) or not prompts:
                raise ValueError("llm-assisted kind requires non-empty prompts mapping")
            for name, text in prompts.items():
                if not isinstance(name, str) or not name or not isinstance(text, str) or not text:
                    raise ValueError("prompt entries must be non-empty str pairs")


def _content_hashes(defn: StrategyDefinition, resolver: SourceResolver) -> dict[str, str]:
    return {
        name: sha256_hex(resolver.get_source(name).encode("utf-8")) for name in sorted(defn.sources)
    }


def _extras_payload(defn: StrategyDefinition) -> dict[str, object]:
    if defn.kind == "deterministic":
        return {"prompts": None, "model_artifact": None, "feature_pipeline": None}
    if defn.kind == "ml":
        pipeline = defn.feature_pipeline
        return {
            "prompts": None,
            "model_artifact": sha256_hex(cast(str, defn.model_artifact).encode("utf-8")),
            "feature_pipeline": (
                sha256_hex(pipeline.encode("utf-8")) if pipeline is not None else None
            ),
        }
    prompts = cast(Mapping[str, str], defn.prompts)
    return {
        "prompts": {name: sha256_hex(text.encode("utf-8")) for name, text in prompts.items()},
        "model_artifact": (
            sha256_hex(defn.model_artifact.encode("utf-8"))
            if defn.model_artifact is not None
            else None
        ),
        "feature_pipeline": (
            sha256_hex(defn.feature_pipeline.encode("utf-8"))
            if defn.feature_pipeline is not None
            else None
        ),
    }


def implementation_fingerprint(defn: StrategyDefinition, resolver: SourceResolver) -> str:
    """Solo bundle: contenido de fuentes declaradas + extras por kind."""
    payload = {"content": _content_hashes(defn, resolver), "extras": _extras_payload(defn)}
    return sha256_hex(canonical_bytes(payload))


def strategy_artifact_identity(defn: StrategyDefinition, resolver: SourceResolver) -> str:
    """Identidad del artifact: id + versión + api + config + impl fingerprint."""
    payload = {
        "strategy_id": defn.strategy_id,
        "strategy_version": defn.strategy_version,
        "strategy_api_version": defn.strategy_api_version,
        "normalized_config": defn.normalized_config,
        "implementation_fingerprint": implementation_fingerprint(defn, resolver),
    }
    return sha256_hex(canonical_bytes(payload))
