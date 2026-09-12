"""Split v1 congelado + guard de protección del holdout (Fase 17C-B).

Fronteras aprobadas por HUMAN_SPLIT_FREEZE_GATE (propuesta 17C-A, sin cambios):

- DEVELOPMENT  = [0, 62208)
- WALK_FORWARD = [62208, 88128)
- FINAL_HOLDOUT = [88128, 103680)

Convención de rangos: [start, end). `is_holdout_range` es el único guard:
devuelve True si el rango de research intersecta el holdout (y por tanto debe
rechazarse). Rangos inválidos fallan cerrado con ValueError.
"""

from __future__ import annotations

DATASET_ID = "BYBIT_ETHBTC_V001"
SPLIT_VERSION = 1
TOTAL_ROWS = 103680

DEVELOPMENT_START = 0
DEVELOPMENT_END = 62208
WALK_FORWARD_START = 62208
WALK_FORWARD_END = 88128
FINAL_HOLDOUT_START = 88128
FINAL_HOLDOUT_END = 103680


def is_holdout_range(start: int, end: int) -> bool:
    """True si [start, end) intersecta FINAL_HOLDOUT (debe rechazarse).

    Fail closed: rangos inválidos (tipos no enteros, start < 0, end > total,
    start >= end) lanzan ValueError en lugar de permitir acceso.
    """
    if isinstance(start, bool) or isinstance(end, bool):
        raise ValueError("range bounds must be integers")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("range bounds must be integers")
    if start < 0 or end > TOTAL_ROWS or start >= end:
        raise ValueError(f"invalid range: [{start}, {end})")
    return start < FINAL_HOLDOUT_END and end > FINAL_HOLDOUT_START
