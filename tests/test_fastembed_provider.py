"""Tests del provider de embeddings local (fastembed, e5-small).

Los unit tests usan un fake determinista; el modelo real se valida como smoke
de evidencia (descarga en primer uso), no en la suite.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import pytest

from application.ports.embeddings import EmbeddingProvider
from domain.memory.space import build_embedding_space
from infrastructure.embeddings.fastembed_provider import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    FastEmbedProvider,
)


class _FakeModel:
    """Sustituye TextEmbedding: vectores deterministas sin red."""

    def __init__(self, model_name: str, dim: int) -> None:
        self.dim = dim
        self.calls: list[tuple[bool, tuple[str, ...]]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 0.0, 0.0][: self.dim] for t in texts]

    def query_embed(self, query: str) -> list[list[float]]:
        self.calls.append((True, (query,)))
        return [[1.0, float(len(query)), 0.0, 0.0][: self.dim]]


def test_provider_satisfies_protocol_and_metadata() -> None:
    provider = FastEmbedProvider(model_factory=lambda name, dim: _FakeModel(name, dim))
    assert isinstance(provider, EmbeddingProvider)
    assert provider.model_name == EMBEDDING_MODEL
    assert provider.dimension == EMBEDDING_DIMENSION == 384


def test_embedding_space_matches_provider() -> None:
    provider = FastEmbedProvider(model_factory=lambda name, dim: _FakeModel(name, dim))
    expected = build_embedding_space("fastembed", EMBEDDING_MODEL, EMBEDDING_DIMENSION)
    assert provider.embedding_space == expected


def test_prefixes_only_for_e5_models() -> None:
    calls: dict[str, list[str]] = {}

    class _Spy:
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            calls.setdefault("texts", []).extend(texts)
            return [[0.0] * EMBEDDING_DIMENSION]

        def query_embed(self, query: str) -> list[list[float]]:
            raise AssertionError("el adapter no debe usar query_embed: prefija él mismo")

    # Modelo por defecto (no e5): texto limpio.
    provider = FastEmbedProvider(model_factory=lambda name, dim: _Spy())
    provider.embed(["texto uno"], is_query=False)
    provider.embed(["pregunta"], is_query=True)
    assert calls["texts"] == ["texto uno", "pregunta"]

    # Variante e5: exige prefijos.
    calls["texts"] = []
    e5 = FastEmbedProvider(
        model_name="intfloat/multilingual-e5-small",
        model_factory=lambda name, dim: _Spy(),
    )
    e5.embed(["texto uno"], is_query=False)
    e5.embed(["pregunta"], is_query=True)
    assert calls["texts"] == ["passage: texto uno", "query: pregunta"]


def test_batch_preserves_order_and_size() -> None:
    class _Identity:
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            return [[float(i)] * EMBEDDING_DIMENSION for i in range(len(texts))]

        def query_embed(self, query: str) -> list[list[float]]:
            return [[-1.0] * EMBEDDING_DIMENSION]

    provider = FastEmbedProvider(model_factory=lambda name, dim: _Identity())
    out = provider.embed(["a", "b", "c"])
    assert len(out) == 3
    assert all(v[0] == i for i, v in enumerate(out))


@pytest.mark.integration
async def test_smoke_real_model_downloads_and_embeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke del modelo real (descarga ~130MB en primer uso). Opt-in explícito."""
    if os.environ.get("RUN_MODEL_SMOKE") != "1":
        pytest.skip("smoke del modelo real requiere RUN_MODEL_SMOKE=1")
    provider = FastEmbedProvider()
    vectors = provider.embed(["passage: momentum positivo"])
    assert len(vectors) == 1 and len(vectors[0]) == EMBEDDING_DIMENSION
