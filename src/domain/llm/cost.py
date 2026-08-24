"""Cálculo del coste de una llamada LLM (PRD §60). Dominio puro.

Los precios se expresan en USD por millón de tokens (``price_*_mtok``) y el coste
resultante es la suma del coste de entrada más el de salida.
"""

from __future__ import annotations

_MILLION = 1_000_000


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    price_input_mtok: float,
    price_output_mtok: float,
) -> float:
    """Coste en USD de una llamada dados tokens y precios por millón de tokens."""
    input_cost = (input_tokens / _MILLION) * price_input_mtok
    output_cost = (output_tokens / _MILLION) * price_output_mtok
    return input_cost + output_cost
