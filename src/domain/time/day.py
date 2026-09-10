"""Abstracción temporal de día calendario UTC (dominio puro).

No usa reloj de pared (`datetime.now()`): deriva el índice de día UTC a partir
del timestamp epoch-milisegundos del evento, de forma determinista y testeable.
"""

MS_PER_DAY = 86_400_000


def utc_day_index(timestamp_ms: int) -> int:
    """Índice de día calendario UTC del timestamp epoch-ms (0 = 1970-01-01)."""
    return timestamp_ms // MS_PER_DAY
