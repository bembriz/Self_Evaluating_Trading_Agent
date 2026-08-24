"""Walk-forward cronológico sin shuffle (PRD §43). Dominio puro.

Ventanas con train expandido: cada ventana entrena en `[0, val_start)` y valida en
`[val_start, val_end)`. El holdout final (últimos `holdout_size` elementos) queda
excluido de toda ventana.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    initial_train: int
    val_size: int
    step: int
    holdout_size: int = 0


class WalkForwardSplitter:
    def __init__(self, config: WalkForwardConfig) -> None:
        if config.initial_train <= 0 or config.val_size <= 0 or config.step <= 0:
            raise ValueError("initial_train, val_size y step deben ser > 0")
        if config.holdout_size < 0:
            raise ValueError("holdout_size debe ser >= 0")
        self._config = config

    def windows(self, n: int) -> list[tuple[int, int]]:
        """Devuelve pares `(val_start, val_end)`; train = `[0, val_start)`."""
        cfg = self._config
        limit = n - cfg.holdout_size
        out: list[tuple[int, int]] = []
        val_start = cfg.initial_train
        while val_start + cfg.val_size <= limit:
            out.append((val_start, val_start + cfg.val_size))
            val_start += cfg.step
        return out
