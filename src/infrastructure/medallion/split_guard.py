"""Guard de splits por día (Bronze) alineado al split v1 congelado.

Fuente de verdad: ``splits/v1.json`` (HUMAN_SPLIT_FREEZE_GATE, dataset
``BYBIT_ETHBTC_V001``, split_version 1):

- DEVELOPMENT      = [2023-09-08T17:45+00, 2025-06-17T17:45+00)
- WALK_FORWARD     = [2025-06-17T17:45+00, 2026-03-14T17:45+00)
- FINAL_HOLDOUT    = [2026-03-14T17:45+00, 2026-08-23T17:30+00)

Un archivo diario solo es permitido si el día entero cae dentro de
DEVELOPMENT (días de borde excluidos: contienen minutos de otra banda).
El guard se ejecuta ANTES de cualquier acceso a la red; ``test_bronze_ingest``
fija estas constantes contra ``splits/v1.json`` para detectar drift.
"""

from __future__ import annotations

from datetime import date

DEVELOPMENT_DATASET_ID = "BYBIT_ETHBTC_V001"
SPLIT_VERSION = 1

DEVELOPMENT_FIRST_TIMESTAMP = "2023-09-08T17:45:00+00:00"
DEVELOPMENT_LAST_TIMESTAMP = "2025-06-17T17:30:00+00:00"
WALK_FORWARD_FIRST_TIMESTAMP = "2025-06-17T17:45:00+00:00"
FINAL_HOLDOUT_FIRST_TIMESTAMP = "2026-03-14T17:45:00+00:00"

# Días COMPLETOS dentro de DEVELOPMENT (excluye días de borde parcial).
DEVELOPMENT_FIRST_DAY = date(2023, 9, 9)
DEVELOPMENT_LAST_DAY = date(2025, 6, 16)


class SplitGuardError(ValueError):
    """Rango fuera de allowed_split (DEVELOPMENT). Fail closed."""


def is_development_day(day: date) -> bool:
    return DEVELOPMENT_FIRST_DAY <= day <= DEVELOPMENT_LAST_DAY


def ensure_development_day(day: date) -> None:
    """Lanza SplitGuardError si el día completo no pertenece a DEVELOPMENT."""
    if isinstance(day, bool) or not isinstance(day, date):
        raise SplitGuardError("day must be a datetime.date")
    if not is_development_day(day):
        raise SplitGuardError(
            f"{day.isoformat()} fuera de DEVELOPMENT "
            f"[{DEVELOPMENT_FIRST_DAY.isoformat()}..{DEVELOPMENT_LAST_DAY.isoformat()}] "
            f"(split v{SPLIT_VERSION}, dataset {DEVELOPMENT_DATASET_ID})"
        )
