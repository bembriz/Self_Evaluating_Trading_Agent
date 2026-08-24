"""Adapter de embeddings locales con fastembed (PRD §33).

Modelo recomendado: `intfloat/multilingual-e5-small` (384 dims, ONNX en CPU).
El modelo se instancia perezosamente (descarga solo en primer uso real); en
tests se inyecta un `model_factory` determinista sin red. e5 exige prefijos
distintos para documentos (`passage:`) y consultas (`query:`): el adapter los
aplica para que el dominio no conozca ese detalle.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSION = 384
PROVIDER_NAME = "fastembed"

ModelFactory = Callable[[str, int], Any]

_DEFAULT_FACTORY: ModelFactory | None = None


def _default_factory() -> ModelFactory:
    global _DEFAULT_FACTORY
    if _DEFAULT_FACTORY is None:
        from fastembed import TextEmbedding

        def factory(model_name: str, dimension: int) -> Any:
            return TextEmbedding(model_name=model_name)

        _DEFAULT_FACTORY = factory
    return _DEFAULT_FACTORY


class FastEmbedProvider:
    """EmbeddingProvider local sobre ONNX (fastembed), espacio versionado."""

    def __init__(
        self,
        *,
        model_name: str = EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
        model_factory: ModelFactory | None = None,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._factory: ModelFactory = model_factory or _default_factory()
        self._loaded_model: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def embedding_space(self) -> str:
        """Identificador versionado del espacio (provider|model|dim)."""
        from domain.memory.space import build_embedding_space

        return build_embedding_space(PROVIDER_NAME, self._model_name, self._dimension)

    def embed(self, texts: Sequence[str], *, is_query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        prefixed = [self._prefix(t, is_query=is_query) for t in texts]
        return [list(map(float, v)) for v in self._ensure_model().embed(prefixed)]

    def _prefix(self, text: str, *, is_query: bool) -> str:
        # Solo la familia e5 exige prefijos query:/passage:; otros modelos van limpios.
        if "e5" not in self._model_name.lower():
            return text
        tag = "query" if is_query else "passage"
        return f"{tag}: {text}"

    def _ensure_model(self) -> Any:
        if self._loaded_model is None:
            self._loaded_model = self._factory(self._model_name, self._dimension)
        return self._loaded_model
