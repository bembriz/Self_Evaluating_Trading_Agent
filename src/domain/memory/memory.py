"""Memoria de trading (PRD §32): registro inmutable de una experiencia cerrada.

Un item solo se crea cuando el trade correspondiente terminó (outcome cerrado),
por lo que `outcome_timestamp_ms` marca cuándo el conocimiento pasó a estar
disponible. El `embedding` es el vector del texto; su espacio se versiona por
(provider, model, dim) — ver `domain.memory.space`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TradingMemory:
    """Experiencia persistible del agente: contexto, resultado y lección.

    Campos de resultado (pnl/mfe/mae/fees/slippage) y versiones permiten auditar
    en qué condiciones se tomó la decisión memorizada (reproducibilidad §38-39).
    """

    id: str
    text: str
    outcome_timestamp_ms: int
    symbol: str = ""
    action: str = ""
    result: str = ""
    pnl: float = 0.0
    mfe: float = 0.0
    mae: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    reflection: str = ""
    strategy_version: str = ""
    prompt_version: str = ""
    llm_model: str = ""
    experiment_id: str = ""
    embedding_space: str = ""
    embedding: tuple[float, ...] = ()
