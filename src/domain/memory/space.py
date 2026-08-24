"""Versionado de espacios de embeddings (PRD §33).

Cada espacio queda identificado por (provider, model, dim): cambiar modelo exige
un espacio nuevo y reindexar; jamás se mezclan vectores de espacios distintos.
"""

from __future__ import annotations

_SEPARATOR = "|"


def build_embedding_space(provider_name: str, model_name: str, dimension: int) -> str:
    """Identificador inmutable del espacio de embeddings."""
    return f"{provider_name}{_SEPARATOR}{model_name}{_SEPARATOR}{dimension}"
