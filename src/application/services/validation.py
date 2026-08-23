"""Validación de calidad/completitud del dataset (PRD §40, data-pipeline-quality)."""

from __future__ import annotations

from dataclasses import dataclass

from domain.market.candle import Candle, Timeframe


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


def validate_candles(candles: list[Candle], timeframe: Timeframe) -> ValidationResult:
    """Comprueba orden, unicidad, alineación y huecos. Nunca descarta filas."""
    errors: list[str] = []
    warnings: list[str] = []
    step_ms = timeframe.minutes * 60_000

    for i, c in enumerate(candles):
        if c.timestamp_ms % step_ms != 0:
            errors.append(f"timestamp no alineado en índice {i}: {c.timestamp_ms}")
        if i == 0:
            continue
        prev = candles[i - 1].timestamp_ms
        if c.timestamp_ms == prev:
            errors.append(f"timestamp duplicado: {c.timestamp_ms}")
        elif c.timestamp_ms < prev:
            errors.append(f"fuera de orden: {c.timestamp_ms} < {prev}")
        elif c.timestamp_ms - prev > step_ms:
            warnings.append(f"hueco entre {prev} y {c.timestamp_ms} (esperado {step_ms} ms)")

    return ValidationResult(tuple(errors), tuple(warnings))
