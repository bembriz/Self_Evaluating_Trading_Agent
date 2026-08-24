"""Modelo de fees reales/configurables de Bybit (PRD §27). Dominio puro.

Las tasas se expresan en puntos básicos (bps): 10 bps = 0.10%. Default taker de
Bybit spot = 0.10%. Versionado para reproducibilidad de experimentos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeeModel:
    taker_bps: float = 10.0
    maker_bps: float = 10.0
    version: str = "bybit-spot-v1"

    @property
    def taker_rate(self) -> float:
        return self.taker_bps / 10_000.0

    def fee(self, notional: float) -> float:
        return notional * self.taker_rate
