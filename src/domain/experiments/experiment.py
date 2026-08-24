"""Experiment tracking (PRD §39): metadata + experiment_id inmutable. Dominio puro.

El `experiment_id` es el hash SHA-256 de la serialización canónica de los parámetros
(no incluye timestamps). Cambiar cualquier parámetro produce un id distinto.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExperimentMetadata:
    git_commit: str = ""
    dataset_version: str = ""
    strategy_version: str = ""
    feature_config_version: str = ""
    fees_model_version: str = ""
    slippage_model_version: str = ""
    prompt_version: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    embedding_provider: str = ""
    embedding_model: str = ""
    risk_config_version: str = ""
    random_seed: int = 0
    params: tuple[tuple[str, str], ...] = ()
    started_at: str = ""
    finished_at: str = ""


def _identity_fields(metadata: ExperimentMetadata) -> tuple[str, ...]:
    return (
        metadata.git_commit,
        metadata.dataset_version,
        metadata.strategy_version,
        metadata.prompt_version,
        metadata.llm_provider,
        metadata.llm_model,
        metadata.embedding_provider,
        metadata.embedding_model,
        metadata.risk_config_version,
        metadata.feature_config_version,
        metadata.fees_model_version,
        metadata.slippage_model_version,
        str(metadata.random_seed),
        repr(sorted(metadata.params)),
    )


def build_experiment_id(metadata: ExperimentMetadata) -> str:
    payload = "|".join(_identity_fields(metadata))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
