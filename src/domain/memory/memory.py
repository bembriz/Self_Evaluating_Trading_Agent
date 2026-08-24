"""Memoria de trading (PRD §32-33): registro inmutable de una experiencia.

El `embedding` es un vector latente opcional (vacío hasta que se integre un
`EmbeddingProvider`); su recuperación por similitud usa pgvector (fases
posteriores). Dominio puro: sin I/O ni frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TradingMemory:
    """Experiencia persistible del agente (texto + vector de embedding opcional)."""

    id: str
    text: str
    outcome_timestamp_ms: int
    embedding: tuple[float, ...] = ()
