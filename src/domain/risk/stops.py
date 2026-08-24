"""Stops deterministas basados en ATR/volatilidad (PRD §23). Dominio puro.

El trailing stop es monótono no decreciente: nunca se aleja del precio aunque
el mercado retroceda (protección de beneficios).
"""

from __future__ import annotations

from domain.risk.config import RiskConfig


def initial_stop(*, entry_price: float, atr: float, config: RiskConfig) -> float:
    """Stop inicial para un largo: entrada − multiplicador × ATR."""
    return entry_price - config.stop_atr_multiplier * atr


def take_profit(*, entry_price: float, stop_loss: float, config: RiskConfig) -> float:
    """Objetivo a R múltiplo del riesgo inicial (entrada − stop)."""
    return entry_price + config.take_profit_r_multiple * (entry_price - stop_loss)


def update_trailing(
    *, current_stop: float, highest_price: float, atr: float, config: RiskConfig
) -> float:
    """Candidato = máximo histórico desde la entrada − mult × ATR; jamás baja."""
    if atr <= 0.0 or highest_price <= 0.0:
        return current_stop
    candidate = highest_price - config.trailing_atr_multiplier * atr
    return max(current_stop, candidate)
