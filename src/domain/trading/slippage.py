"""Modelo de slippage conservador parametrizado (PRD §28). Dominio puro.

Para históricos sin order book no hay spread/depth reales, así que se aplica un
coste por lado en puntos básicos (default 2 bps = 0.02% por lado), conservador y
parametrizable. Versionado para reproducibilidad.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlippageModel:
    bps: float = 2.0
    version: str = "conservative-v1"

    @property
    def rate(self) -> float:
        return self.bps / 10_000.0

    def cost(self, notional: float) -> float:
        return notional * self.rate
