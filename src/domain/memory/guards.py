"""Guards anti data-leakage en recuperación de memoria (PRD §34). Dominio puro.

Una decisión en T solo puede usar memoria cuyo conocimiento existiera antes de T:
`memory.outcome_timestamp_ms < decision_timestamp_ms`, estricto.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.memory.memory import TradingMemory


class MemoryLeakageError(Exception):
    """Se detectó un intento de usar memoria con outcome posterior a la decisión."""


def filter_leakage(
    items: Iterable[TradingMemory], *, decision_timestamp_ms: int
) -> tuple[TradingMemory, ...]:
    """Devuelve solo los items con outcome estrictamente anterior a la decisión."""
    return tuple(item for item in items if item.outcome_timestamp_ms < decision_timestamp_ms)


def assert_no_leakage(items: Iterable[TradingMemory], *, decision_timestamp_ms: int) -> None:
    """Lanza `MemoryLeakageError` si algún item usa información futura."""
    for item in items:
        if item.outcome_timestamp_ms >= decision_timestamp_ms:
            raise MemoryLeakageError(
                f"leakage: memoria {item.id} con outcome {item.outcome_timestamp_ms} "
                f">= decision {decision_timestamp_ms}"
            )
