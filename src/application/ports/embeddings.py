"""Puerto del proveedor de embeddings (PRD §33). Independiente del runtime."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Convierte textos en vectores. Espacio versionado por (model, dim).

    `is_query=True` permite al adapter aplicar el prefijo adecuado (p. ej. e5
    distingue `query:` de `passage:`) sin filtrar detalles al dominio.
    """

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]: ...
