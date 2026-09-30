"""Guard de splits por día para operaciones de ingesta/transformación Medallion.

Fuente de verdad: ``splits/v1.json`` (HUMAN_SPLIT_FREEZE_GATE, dataset
``BYBIT_ETHBTC_V001``, split_version 1):

- DEVELOPMENT      = [2023-09-08T17:45+00, 2025-06-17T17:45+00)
- WALK_FORWARD     = [2025-06-17T17:45+00, 2026-03-14T17:45+00)
- FINAL_HOLDOUT    = [2026-03-14T17:45+00, 2026-08-23T17:30+00)
- FUTURE_COLLECTION >= 2026-08-24 (posterior al holdout congelado)

Un archivo diario solo es permitido si el día entero cae dentro de una clase de
acceso autorizada. El DEFAULT de Bronze/Silver/Candles es ``DEVELOPMENT_ONLY``;
solo una autorización explícita (``IngestScope``) habilita FUTURE_COLLECTION.
WALK_FORWARD y FINAL_HOLDOUT están SIEMPRE bloqueados, incluso con autorización
future: nunca se desbloquea Gold/research/replay/tuning.

El guard se ejecuta ANTES de cualquier acceso a la red o disco; los tests fijan
estas constantes contra ``splits/v1.json`` para detectar drift.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

DEVELOPMENT_DATASET_ID = "BYBIT_ETHBTC_V001"
SPLIT_VERSION = 1

DEVELOPMENT_FIRST_TIMESTAMP = "2023-09-08T17:45:00+00:00"
DEVELOPMENT_LAST_TIMESTAMP = "2025-06-17T17:30:00+00:00"
WALK_FORWARD_FIRST_TIMESTAMP = "2025-06-17T17:45:00+00:00"
FINAL_HOLDOUT_FIRST_TIMESTAMP = "2026-03-14T17:45:00+00:00"

# Límites por día COMPLETO (excluye días de borde parcial).
DEVELOPMENT_FIRST_DAY = date(2023, 9, 9)
DEVELOPMENT_LAST_DAY = date(2025, 6, 16)
WALK_FORWARD_FIRST_DAY = date(2025, 6, 17)
FINAL_HOLDOUT_FIRST_DAY = date(2026, 3, 14)
FINAL_HOLDOUT_LAST_DAY = date(2026, 8, 23)
FUTURE_COLLECTION_FIRST_DAY = date(2026, 8, 24)


class SplitGuardError(ValueError):
    """Rango fuera de la clase de acceso autorizada. Fail closed."""


class IngestClass(StrEnum):
    """Clase de acceso de un día para ingesta/transformación Medallion."""

    DEVELOPMENT = "DEVELOPMENT"
    WALK_FORWARD = "WALK_FORWARD"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"
    FUTURE_COLLECTION = "FUTURE_COLLECTION"
    OUT_OF_RANGE = "OUT_OF_RANGE"


class IngestScope(StrEnum):
    """Política explícita de qué clases de acceso puede ingerir un caller."""

    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    DEVELOPMENT_AND_FUTURE_COLLECTION = "DEVELOPMENT_AND_FUTURE_COLLECTION"


DEFAULT_INGEST_SCOPE = IngestScope.DEVELOPMENT_ONLY
PHASE24_INGEST_SCOPE = IngestScope.DEVELOPMENT_AND_FUTURE_COLLECTION


def _require_day(day: date) -> None:
    if isinstance(day, bool) or not isinstance(day, date):
        raise SplitGuardError("day must be a datetime.date")


def classify_ingest_day(day: date) -> IngestClass:
    """Clasifica un día por su clase de acceso (fail-closed para fuera de rango)."""
    _require_day(day)
    if DEVELOPMENT_FIRST_DAY <= day <= DEVELOPMENT_LAST_DAY:
        return IngestClass.DEVELOPMENT
    if WALK_FORWARD_FIRST_DAY <= day < FINAL_HOLDOUT_FIRST_DAY:
        return IngestClass.WALK_FORWARD
    if FINAL_HOLDOUT_FIRST_DAY <= day <= FINAL_HOLDOUT_LAST_DAY:
        return IngestClass.FINAL_HOLDOUT
    if day >= FUTURE_COLLECTION_FIRST_DAY:
        return IngestClass.FUTURE_COLLECTION
    return IngestClass.OUT_OF_RANGE


def is_development_day(day: date) -> bool:
    return classify_ingest_day(day) is IngestClass.DEVELOPMENT


def ensure_ingest_allowed(day: date, *, scope: IngestScope = DEFAULT_INGEST_SCOPE) -> IngestClass:
    """Autoriza (o bloquea fail-closed) la ingesta de ``day`` según ``scope``.

    - DEVELOPMENT: permitido en cualquier scope.
    - FUTURE_COLLECTION: permitido SOLO con ``DEVELOPMENT_AND_FUTURE_COLLECTION``.
    - WALK_FORWARD / FINAL_HOLDOUT / OUT_OF_RANGE: SIEMPRE bloqueados.
    """
    _require_day(day)
    if not isinstance(scope, IngestScope):
        raise SplitGuardError("scope must be an IngestScope (not a bool/str)")
    access = classify_ingest_day(day)
    if access is IngestClass.DEVELOPMENT:
        return access
    if access is IngestClass.FUTURE_COLLECTION and (
        scope is IngestScope.DEVELOPMENT_AND_FUTURE_COLLECTION
    ):
        return access
    raise SplitGuardError(
        f"{day.isoformat()} bloqueado para ingesta: clase {access.value} "
        f"no autorizada por scope {scope.value} "
        f"(split v{SPLIT_VERSION}, dataset {DEVELOPMENT_DATASET_ID})"
    )


def ensure_development_day(day: date) -> None:
    """Lanza SplitGuardError si el día completo no pertenece a DEVELOPMENT."""
    ensure_ingest_allowed(day, scope=DEFAULT_INGEST_SCOPE)
