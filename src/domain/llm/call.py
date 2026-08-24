"""Registro inmutable de una llamada LLM (PRD §18, §60). Dominio puro.

Captura la identidad del proveedor/modelo, los hashes de prompt y de estado de
mercado (para trazabilidad causal), métricas de latencia/tokens y el coste calculado.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    """Llamada individual al LLM con su coste y contexto causal."""

    provider: str
    requested_model: str
    reported_model_version: str
    request: str
    response: str
    prompt_hash: str
    market_state_hash: str
    temperature: float
    parameters: tuple[tuple[str, str], ...]
    timestamp_ms: int
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str = ""
