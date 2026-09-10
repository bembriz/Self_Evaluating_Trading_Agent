"""Productor del certification-state schema v2 (16c.6).

Convierte estado real persistido (resumen, eventos, velas) + artefacto runtime en
el JSON v2 que consume harness/scripts/paper_certification.py. frozen es
inmutable (ancla de certificación); current se refresca en cada escritura y
lleva las mismas 10 claves que frozen (el evaluador compara frozen vs current
clave a clave para detectar drift de versiones / re-ancla del reloj).

Invariante mark-sensitive de la reconciliación (16c.6 / Task 4b-L2):
``accounting_book`` se persiste con la equity marcada a mercado con el close de la
última vela persistida en el momento del ancla. Al comparar el libro previo contra
la reconstrucción actual, ``equity(book) == reconstructed_equity`` sólo se cumple
si ambas usan el MISMO mark; en la práctica, un proceso continuo re-persiste el
libro en cada escritura PASS con el mark de ese momento (flat o mark constante),
de modo que el residual exacto == 0 no produce falsos FAIL diarios. Este módulo
NUNCA aplica tolerancia al residual: la invarianza exige ``accounting_residual == 0``
exacto, y cualquier estado no auditable (libro ilegible / MissingMarkError /
reconciliation error) se traduce a residual ``None``/``"0"`` (JSON estricto, sin
NaN) + ``accounting_status`` FAIL + ``accounting_failure_reason`` + critical_error,
nunca a un 0 artificial ni a ``Decimal("NaN")``.

Reloj de certificación explícito (16c.6 / Task 5b): ``_resolve_frozen`` NUNCA
auto-ancla. Escribir periódicamente antes de un START explícito produce un estado
``NOT_STARTED`` (``frozen.certification_started_at is None``, clave presente con
valor null para preservar la paridad de las 10 claves). El ancla UTC sólo se crea
vía ``start_certification`` (operador / CLI del runner, Task 7): una sola vez por
certificación, conservada intacta en restarts y reescrituras. Legacy 0.1.x nunca
aporta ancla v2.

Preservación del ancla (16c.6 / Task 8d, corrección de pérdida silenciosa): mientras
la certificación esté ANCLADA (``frozen.certification_started_at`` presente, fase
``RUNNING``) el bloque ``frozen`` se conserva byte a byte REGARDLESS de cualquier
drift del artefacto — versiones/commit Y también symbol/timeframe. Un artefacto que
driftó en ``strategy_version``/``application_version``/``git_commit``/``symbol``/
``timeframe`` conserva el frozen anclado y ``current`` refleja el artefacto ⇒ el
evaluador emite ``frozen_versions`` FAIL **sin re-anclar el reloj ni perder la
certificación en curso**. Sólo un estado SIN ancla (ausente / legacy / NOT_STARTED)
produce un bloque nuevo NOT_STARTED (ancla ``None``); el ancla del reloj sólo se crea
vía ``start_certification`` (y sólo desde NOT_STARTED/INVALIDATED). Un upgrade
intencional exige el flujo explícito invalidate → archive → nuevo
``--start-certification``.

Regla de libro (16c.6 / Task 4b-L1 + 8c F2): clave ``accounting_book`` AUSENTE
(primer ancla v2) ⇒ baseline PASS y se persiste el libro reconstruido. Clave
PRESENTE pero inparseable (``BookState.from_dict`` -> None) ⇒ FAIL-closed:
residual ``None`` + ``accounting_status = "FAIL"`` + reason
``"unparseable_accounting_book"`` + critical_error ``{"message": "unparseable
accounting_book", "explained": False}`` (prohibido degradar silenciosamente a
baseline). El libro es ahora un checkpoint con CURSOR (``last_event_ms``) que el
reconciliador three-way (accounting_reconciliation.reconcile_with_book) avanza
sólo en PASS; una serialización sin cursor (pre-8c) se re-baselinea en el
reconciliador (reconcile_with_book devuelve PASS baseline) — nunca desplegado,
sin migración real. Con ``status == "PASS"`` el productor persiste
``reconciliation.book.to_dict()`` (checkpoint con cursor actualizado).

JSON estricto (16c.6 / Task 5b): ninguna escritura v2 puede contener valores
no-finitos (``float``/``Decimal`` NaN, ±Infinity) en ningún campo numérico ni la
cadena ``"NaN"``. Donde un valor de origen no sea finito se emite ``null`` según
semántica; ``json.dumps(state, allow_nan=False)`` nunca lanza sobre un estado del
productor.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.ports.paper_trading import PaperTradeEvent
from application.services.accounting_reconciliation import BookState
from domain.market.candle import Candle
from domain.risk.config import RiskConfig
from domain.trading.fees import FeeModel
from domain.trading.slippage import SlippageModel

if TYPE_CHECKING:  # evita ciclo de import con paper_runner (Task 5)
    from application.services.accounting_reconciliation import ReconciliationResult
    from application.services.paper_runner import PaperRunSummary

FEES_SLIPPAGE_CONFIG_VERSION = f"{FeeModel().version}+{SlippageModel().version}"

# Único origen en el productor de las 10 claves congeladas (paridad con
# harness/scripts/paper_certification.py::FROZEN_VERSION_KEYS, verificada por
# test en Task 5). Orden canónico = orden del evaluador.
FROZEN_VERSION_KEYS: tuple[str, ...] = (
    "git_commit",
    "application_version",
    "strategy_version",
    "risk_config_version",
    "docker_image_digest",
    "symbol",
    "timeframe",
    "initial_capital",
    "fees_slippage_config_version",
    "certification_started_at",
)

# Campos de identidad OBLIGATORIOS no vacíos para anclar una certificación
# (Task 8b/A): mercado (symbol/timeframe), versiones de build
# (git_commit/application_version/docker_image_digest) y de configuración
# (strategy_version/risk_config_version/fees_slippage_config_version). Un START
# con cualquiera vacío se RECHAZA (sin anchor) — en una sesión prístina (0
# eventos) la identidad se resuelve desde la config del runner, nunca queda "".
START_IDENTITY_FIELDS: tuple[str, ...] = (
    "symbol",
    "timeframe",
    "git_commit",
    "application_version",
    "strategy_version",
    "risk_config_version",
    "docker_image_digest",
    "fees_slippage_config_version",
)


def _iso_utc_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def session_started_at_ms(summary: PaperRunSummary, now_ms: int) -> int:
    return summary.first_timestamp_ms if summary.first_timestamp_ms is not None else now_ms


@dataclass(frozen=True, slots=True)
class RuntimeArtifact:
    git_commit: str
    application_version: str
    docker_image_digest: str
    strategy_version: str
    strategy_hash: str
    risk_config_version: str
    fees_slippage_config_version: str
    symbol: str
    timeframe: str
    initial_capital: float
    # Sesión de la corrida (Task 8c/F1): nunca vacía cuando el START se ancla;
    # identidad del envelope v2 que `start_certification` escribe directamente.
    session_id: str
    # Mantenido por paridad de contrato con el wiring del runner (Task 7); el reloj
    # de certificación v2 NO se ancla desde aquí (sólo vía start_certification).
    certification_started_at_ms: int | None


def _identity_blank(value: object) -> bool:
    """True si un campo de identidad está vacío (None o cadena sin caracteres visibles)."""
    return value is None or (isinstance(value, str) and not value.strip())


def _resolve_identity_field(persisted: str, configured: str) -> str:
    """Campo de identidad resuelto: valor persistido no vacío, si no el configurado."""
    return persisted.strip() or configured


def _assert_no_session_conflict(
    *,
    persisted_symbol: str,
    persisted_timeframe: str,
    configured_symbol: str,
    configured_timeframe: str,
) -> None:
    """Rechaza una identidad persistida que contradice la config del runner (Task 8b/A).

    La resolución "persistido si existe, si no config" sólo RELLENA huecos: si el
    valor persistido (no vacío) contradice la config, elegir persistido etiquetaría
    mal el mercado que el runner realmente transmite y elegir config abandonaría
    silenciosamente la sesión persistida ⇒ error fail-fast (sin artefacto ni ancla
    con identidad inconsistente). strategy_version queda fuera: su drift es una
    condición gestionada aparte (frozen_versions FAIL sin re-ancla), no un conflicto
    de sesión.
    """
    if persisted_symbol and configured_symbol and persisted_symbol != configured_symbol:
        raise ValueError(
            "START rejected: persisted session symbol "
            f"{persisted_symbol!r} conflicts with configured symbol {configured_symbol!r}; "
            "align symbols/timeframe with the persisted session (or invalidate/archive "
            "and use a fresh state path) before starting a certification"
        )
    if persisted_timeframe and configured_timeframe and persisted_timeframe != configured_timeframe:
        raise ValueError(
            "START rejected: persisted session timeframe "
            f"{persisted_timeframe!r} conflicts with configured timeframe "
            f"{configured_timeframe!r}; align symbols/timeframe with the persisted session "
            "(or invalidate/archive and use a fresh state path) before starting a certification"
        )


def runtime_artifact(
    *,
    summary: PaperRunSummary,
    app_version: str,
    git_commit: str,
    docker_image_digest: str,
    risk_config: RiskConfig,
    now_ms: int,
    default_symbol: str = "",
    default_timeframe: str = "",
    default_strategy_version: str = "",
    default_session_id: str = "",
) -> RuntimeArtifact:
    """Artefacto de identidad nunca vacía (Task 8b/A + 8c/F1).

    ``symbol``/``timeframe``/``strategy_version`` se resuelven como: valor persistido
    de la sesión (``summary``) si existe y es no vacío, ELSE la config del runner
    (``default_symbol`` = ``symbols[0]``, ``default_timeframe`` = ``timeframe.label``,
    ``default_strategy_version`` = ``EmaRsiBaseline.version``) — una sesión prístina
    con 0 eventos jamás produce identidad "". Si el valor persistido (no vacío)
    contradice la config (``default_*`` no vacío), se lanza ``ValueError`` (conflicto
    de sesión): nunca se resuelve silenciosamente a favor de uno.

    ``session_id`` se resuelve igual: valor persistido del summary si existe, ELSE
    ``default_session_id`` (la sesión que el runner configuró, vía CLI/settings),
    ELSE el default derivado ``paper-baseline-{timeframe}-{symbol}`` (mismo formato
    que el ``_default_session_id`` del CLI); el START de una sesión prístina nunca
    ancla un envelope con ``session_id`` vacío.
    """
    resolved_symbol = _resolve_identity_field(summary.symbol, default_symbol)
    resolved_timeframe = _resolve_identity_field(summary.timeframe, default_timeframe)
    _assert_no_session_conflict(
        persisted_symbol=summary.symbol,
        persisted_timeframe=summary.timeframe,
        configured_symbol=default_symbol,
        configured_timeframe=default_timeframe,
    )
    session_id = _resolve_identity_field(summary.session_id, default_session_id)
    if not session_id:
        session_id = f"paper-baseline-{resolved_timeframe}-{resolved_symbol.lower()}"
    return RuntimeArtifact(
        git_commit=git_commit,
        application_version=app_version,
        docker_image_digest=docker_image_digest,
        strategy_version=_resolve_identity_field(
            summary.strategy_version, default_strategy_version
        ),
        strategy_hash=summary.strategy_hash,
        risk_config_version=risk_config.version,
        fees_slippage_config_version=FEES_SLIPPAGE_CONFIG_VERSION,
        symbol=resolved_symbol,
        timeframe=resolved_timeframe,
        initial_capital=risk_config.capital,
        session_id=session_id,
        # Candidata histórica; el reloj v2 se ancla vía start_certification.
        certification_started_at_ms=now_ms,
    )


def _version_block(artifact: RuntimeArtifact, started_at_iso: str | None) -> dict[str, object]:
    """Bloque de las 10 claves canónicas (orden de ``FROZEN_VERSION_KEYS``).

    Un único constructor compartido por frozen/current: `certification_started_at`
    es la única clave que no sale del artefacto observado y puede ser ``None``
    (estado NOT_STARTED, sin ancla) o un ISO-8601 UTC con sufijo ``Z`` (RUNNING).
    """
    return {
        "git_commit": artifact.git_commit,
        "application_version": artifact.application_version,
        "strategy_version": artifact.strategy_version,
        "risk_config_version": artifact.risk_config_version,
        "docker_image_digest": artifact.docker_image_digest,
        "symbol": artifact.symbol,
        "timeframe": artifact.timeframe,
        "initial_capital": artifact.initial_capital,
        "fees_slippage_config_version": artifact.fees_slippage_config_version,
        "certification_started_at": started_at_iso,
    }


def _frozen_block(artifact: RuntimeArtifact, started_at_ms: int) -> dict[str, object]:
    return _version_block(artifact, _iso_utc_ms(started_at_ms))


def _current_block(artifact: RuntimeArtifact, *, started_at_iso: str | None) -> dict[str, object]:
    return _version_block(artifact, started_at_iso)


def _resolve_frozen(previous: Mapping[str, Any], artifact: RuntimeArtifact) -> dict[str, object]:
    """Frozen de esta escritura: NUNCA auto-ancla.

    Si la certificación previa está ANCLADA (``certification_started_at`` presente,
    fase ``RUNNING``) conserva ``previous.frozen`` intacto (byte a byte) REGARDLESS
    de cualquier drift del artefacto (symbol/timeframe/versiones/commit): el ancla
    jamás se pierde silenciosamente y el evaluador reporta ``frozen_versions`` FAIL
    sin re-anclar. Sólo un estado sin ancla (ausente, legacy plano o NOT_STARTED)
    devuelve un bloque v2 con las 10 claves y ``certification_started_at = None``
    (NOT_STARTED). El ancla del reloj sólo se materializa vía ``start_certification``.
    """
    raw = previous.get("frozen")
    frozen: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    if certification_phase(previous) == "RUNNING":
        return dict(frozen)
    return _version_block(artifact, None)


def certification_phase(state: Mapping[str, Any]) -> str:
    """Fase del reloj de certificación: ``NOT_STARTED`` | ``RUNNING`` | ``INVALIDATED``.

    ``INVALIDATED`` si ``status == "INVALIDATED"``; ``RUNNING`` si
    ``frozen.certification_started_at`` tiene un valor ISO (ancla presente y estado
    no invalidado); en cualquier otro caso ``NOT_STARTED`` (sin ancla ⇒ el evaluador
    falla ``calendar_days`` por age ``None``: un estado sin START nunca puede PASS).
    """
    if state.get("status") == "INVALIDATED":
        return "INVALIDATED"
    raw = state.get("frozen")
    if isinstance(raw, Mapping):
        started = raw.get("certification_started_at")
        if isinstance(started, str) and started.strip():
            return "RUNNING"
    return "NOT_STARTED"


def missing_start_identity(artifact: RuntimeArtifact) -> list[str]:
    """Campos obligatorios de identidad del START vacíos (Task 8b/A), en orden canónico.

    ``START_IDENTITY_FIELDS`` son los 8 campos no-negociables de un artefacto para
    anclar una certificación; ``[]`` significa artefacto completo. Vacío = None o
    cadena sin caracteres visibles.
    """
    return [field for field in START_IDENTITY_FIELDS if _identity_blank(getattr(artifact, field))]


def session_context_conflict(previous: Mapping[str, Any], artifact: RuntimeArtifact) -> str | None:
    """Conflicto de contexto de sesión entre el estado persistido y el artefacto.

    Si el ``frozen`` previo ya registra un contexto de sesión (``symbol``/``timeframe``
    no vacíos) que difiere del artefacto ⇒ devuelve la razón del conflicto. Anclar un
    START ahí crearía una identidad inconsistente o pisaría una certificación (otra
    sesión) en curso; un upgrade intencional exige invalidate → archive → nuevo START.
    Sin contexto previo (fichero ausente / legacy plano / frozen sin sesión) ⇒ ``None``.
    """
    raw = previous.get("frozen")
    frozen: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    for field in ("symbol", "timeframe"):
        persisted = frozen.get(field)
        current = getattr(artifact, field)
        if isinstance(persisted, str) and persisted.strip() and persisted != current:
            return (
                f"previous frozen session {field}={persisted!r} conflicts with artifact "
                f"{field}={current!r}; START would anchor an inconsistent identity"
            )
    return None


def start_certification(
    previous: Mapping[str, Any], artifact: RuntimeArtifact, *, now_ms: int
) -> dict[str, Any]:
    """Materializa el ancla UTC del reloj de certificación (operador / CLI Task 7).

    - **Validación de START (Task 8b/A, fail-closed):** si falta alguno de los 8
      campos obligatorios de identidad del artefacto (``missing_start_identity``) o
      el estado previo registra un contexto de sesión en conflicto
      (``session_context_conflict``) ⇒ ``ValueError`` **sin anclar nada**: el estado
      previo queda intacto (``certification_started_at`` sigue ``None`` / fase
      NOT_STARTED) y el CLI loguea el rechazo al operador.
    - **Envelope v2 COMPLETO (Task 8c/F1):** al anclar (NOT_STARTED → anchor;
      INVALIDATED → anchor fresco) devuelve un documento ``schema_version: 2`` con
      `session_id` (del estado previo si existe, si no del artefacto, nunca vacía),
      `session_started_at` (ISO del ancla o del previo si existe), `frozen` con las
      10 claves y el anchor, `current` espejando el MISMO anchor (sin drift),
      `operational` presente (skeleton vacío si no hay evidencia previa; el
      productor periódico lo rellena), `accounting_book` (preserva el previo si
      existe, si no ``None``), `application_version` top-level SIEMPRE del artefacto
      y `strategy_version`/`strategy_hash`/`active_strategy_hash` rellenadas desde
      el artefacto si el previo no las trae — mismas claves de identidad top-level
      del productor periódico, para que la primera escritura periódica no emita un
      `state_continuity == "FAIL"` espurio — y `status`/`invalidated_reason` en
      ``None``. Sin heurística {frozen,current}⇒v2: el routing por `schema_version`
      (Task 8b) encuentra un fichero v2 desde el primer arranque en limpio.
    - ``NOT_STARTED`` o sin frozen compatible ⇒ copia con
      ``frozen.certification_started_at = _iso_utc_ms(now_ms)`` (anchor nuevo);
      ``current`` se recompone con el MISMO anchor para no inducir drift.
    - ``RUNNING`` (cualquier contexto) ⇒ **no-op** (devuelve la copia intacta: la
      segunda llamada NO re-ancla jamás, ni siquiera si el artefacto driftó en
      versiones/commit; un contexto de sesión distinto lo rechaza antes
      ``session_context_conflict``; un upgrade intencional exige invalidar primero:
      invalidate → archive → nuevo START).
    - ``INVALIDATED`` ⇒ copia con anchor fresco (``_iso_utc_ms(now_ms)``) que
      reemplaza el frozen previo y limpia ``status``/``invalidated_reason``.
    """
    missing = missing_start_identity(artifact)
    if missing:
        raise ValueError(
            "START rejected: missing mandatory identity field(s): " + ", ".join(missing)
        )
    conflict = session_context_conflict(previous, artifact)
    if conflict is not None:
        raise ValueError(f"START rejected: {conflict}")
    phase = certification_phase(previous)
    if phase == "RUNNING":
        return dict(previous)

    anchor = _iso_utc_ms(now_ms)
    state = dict(previous)
    state["schema_version"] = 2
    session_id = previous.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        session_id = artifact.session_id.strip()
    if not session_id:
        session_id = f"paper-baseline-{artifact.timeframe}-{artifact.symbol.lower()}"
    state["session_id"] = session_id
    previous_started = previous.get("session_started_at")
    state["session_started_at"] = (
        previous_started
        if isinstance(previous_started, str) and previous_started.strip()
        else anchor
    )
    new_frozen = _frozen_block(artifact, now_ms)
    state["frozen"] = new_frozen
    state["current"] = _current_block(artifact, started_at_iso=anchor)
    # Simetría con el productor periódico (Task 8c/F1 follow-up): el envelope de
    # START lleva las mismas claves de identidad top-level que escribe
    # `build_certification_state_v2`, de modo que la PRIMERA escritura periódica
    # sobre este doc no produce un `state_continuity == "FAIL"` espurio.
    # `application_version` es la clave que compara `state_continuity`
    # (previous.schema_version == 2 => previous.application_version == actual) y se
    # fija SIEMPRE al artefacto al anclar (la certificación nueva corre en el
    # build actual); las claves strategy_* de compatibilidad de lectura se rellenan
    # desde el artefacto sólo si el previo no las trae (legacy/ausente).
    state["application_version"] = artifact.application_version
    state.setdefault("strategy_version", artifact.strategy_version)
    state.setdefault("strategy_hash", artifact.strategy_hash)
    state.setdefault("active_strategy_hash", artifact.strategy_hash)
    if not isinstance(state.get("operational"), Mapping):
        state["operational"] = {}
    if "accounting_book" not in state:
        state["accounting_book"] = None
    state["status"] = None
    state["invalidated_reason"] = None
    return state


_METRICS_HEARTBEATS_KEY = "metrics_heartbeats"


def decision_context_coverage(events: Sequence[PaperTradeEvent]) -> float:
    """% de eventos con `decision_context` completo (schema_version + signal_reason)."""
    if not events:
        return 100.0
    covered = sum(
        1
        for e in events
        if e.decision_context is not None
        and "schema_version" in e.decision_context
        and "signal_reason" in e.decision_context
    )
    return 100.0 * covered / len(events)


def fill_counts(events: Sequence[PaperTradeEvent]) -> tuple[int, int, int]:
    """(fill_count, closed_trade_count, trade_count).

    fill_count = eventos con `filled`; closed = SELL con `exit_reason` no vacío;
    trade_count es alias de fill_count (todo fill es trade).
    """
    fills = [e for e in events if e.filled]
    closed = sum(1 for e in fills if e.action == "SELL" and e.exit_reason != "")
    count = len(fills)
    return (count, closed, count)


def slippage_and_fees(events: Sequence[PaperTradeEvent]) -> tuple[float, float]:
    """Sumas agregadas de `slippage_cost` y `fee`."""
    return (sum(e.slippage_cost for e in events), sum(e.fee for e in events))


def unexplained_gap_count(candles: Sequence[Candle], interval_ms: int) -> int:
    """Buckets `interval_ms` faltantes entre la primera y última vela de la lista.

    La lista llega ordenada por `timestamp_ms` ascendente (el caller ya la scopeó a
    `timestamp_ms <= now_ms`); cuenta huecos enteros entre velas consecutivas.
    """
    if len(candles) < 2 or interval_ms <= 0:
        return 0
    gaps = 0
    prev = candles[0].timestamp_ms
    for candle in candles[1:]:
        ts = candle.timestamp_ms
        expected = prev + interval_ms
        if ts > expected:
            gaps += (ts - expected) // interval_ms
        prev = ts
    return gaps


def market_evidence_complete(
    unexplained_gaps: int,
    candles: Sequence[Candle],
    events: Sequence[PaperTradeEvent],
) -> str:
    """PASS si no hay huecos sin explicar y la primera/last vela acotan los eventos.

    Sin eventos no hay rango que acotar: PASS con `unexplained_gaps == 0`. Con
    eventos pero sin velas no hay evidencia de mercado: FAIL.
    """
    if unexplained_gaps != 0:
        return "FAIL"
    if not events:
        return "PASS"
    if not candles:
        return "FAIL"
    first = candles[0].timestamp_ms
    last = candles[-1].timestamp_ms
    event_ts = [e.timestamp_ms for e in events]
    if first <= min(event_ts) and last >= max(event_ts):
        return "PASS"
    return "FAIL"


def metrics_history_days(heartbeats: Sequence[str]) -> int:
    """N.º de fechas UTC distintas (`YYYY-MM-DD`) con heartbeat confirmado."""
    return len(set(heartbeats))


def add_metrics_heartbeat(previous: Mapping[str, Any], today: str, artifact_ok: bool) -> list[str]:
    """Añade `today` (dedup) al histórico de heartbeats solo si `artifact_ok`.

    Conserva las entradas previas del estado (clave `metrics_heartbeats`) y devuelve
    la lista resultante sin mutar `previous`.
    """
    raw = previous.get(_METRICS_HEARTBEATS_KEY)
    heartbeats: list[str] = [h for h in raw if isinstance(h, str)] if isinstance(raw, list) else []
    if artifact_ok and today not in heartbeats:
        heartbeats.append(today)
    return heartbeats


def state_continuity(
    previous: Mapping[str, Any], *, application_version: str, session_id: str
) -> str:
    """PASS si es el primer ancla (schema != 2) o la sesión v2 previa no derivó."""
    if previous.get("schema_version") != 2:
        return "PASS"
    if (
        previous.get("application_version") == application_version
        and previous.get("session_id") == session_id
    ):
        return "PASS"
    return "FAIL"


def recovery_integrity(critical_errors: Sequence[Mapping[str, Any]]) -> str:
    """PASS si no hay ningún error crítico de tipo `recovery_divergence`."""
    if any(err.get("kind") == "recovery_divergence" for err in critical_errors):
        return "FAIL"
    return "PASS"


# ---------------------------------------------------------------------------
# Task 5: safeguard evidence fail-closed + composición v2 + escritura crash-safe
# ---------------------------------------------------------------------------

_SAFEGUARD_ARTIFACT_KEYS: tuple[str, ...] = (
    "git_commit",
    "application_version",
    "docker_image_digest",
    "strategy_version",
    "risk_config_version",
)

# Secuencias COMPLETAS de cada drill operativo (Task 6, harness). El drill sólo
# emite `status == "PASS"` tras completar TODOS los pasos en orden; el matcher
# exige la igualdad exacta con la secuencia canónica (fail-closed: evidencia
# ausente, artefacto distinto, drill incompleto o risk_config_version distinta
# ⇒ False).
_KILL_SWITCH_DRILL_STEPS: tuple[str, ...] = (
    "activate",
    "buy_rejected",
    "persist",
    "restart_still_active",
    "buy_still_rejected",
    "operator_reset",
)
_DAILY_LOSS_DRILL_STEPS: tuple[str, ...] = (
    "daily_loss_exceeded",
    "buy_rejected",
    "sell_allowed",
    "restart_persists",
    "utc_rollover_reset",
)
_SAFEGUARD_DRILL_STEPS: dict[str, tuple[str, ...]] = {
    "kill_switch": _KILL_SWITCH_DRILL_STEPS,
    "daily_loss": _DAILY_LOSS_DRILL_STEPS,
}


def _normalized_version_value(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value.strip()
    return value


def safeguard_passes(
    safeguard_evidence: Mapping[str, Any], kind: str, frozen: Mapping[str, object]
) -> bool:
    """Evidencia de drill COMPLETA y ligada al artefacto congelado (fail-closed).

    PASS sólo si existe una entrada para `kind` con `status == "PASS"`, su `type`
    coincide EXACTAMENTE con `kind` (Task 8b/C: una entrada de otro drill — p. ej.
    un daily_loss colado bajo la clave kill_switch — nunca hace PASS), sus 5
    claves de `artifact` coinciden con `frozen` (normalización trim/int↔float) y
    sus `steps` son exactamente la secuencia completa del drill.
    """
    expected_steps = _SAFEGUARD_DRILL_STEPS.get(kind)
    if expected_steps is None:
        return False
    entry = safeguard_evidence.get(kind)
    if not isinstance(entry, Mapping):
        return False
    if entry.get("type") != kind:
        return False
    if entry.get("status") != "PASS":
        return False
    artifact = entry.get("artifact")
    if not isinstance(artifact, Mapping):
        return False
    for key in _SAFEGUARD_ARTIFACT_KEYS:
        if _normalized_version_value(artifact.get(key)) != _normalized_version_value(
            frozen.get(key)
        ):
            return False
    steps = entry.get("steps")
    return isinstance(steps, list) and steps == list(expected_steps)


@dataclass(frozen=True, slots=True)
class OperationalFacts:
    """Hechos operacionales del estado v2 (se persisten bajo `operational`).

    ``accounting_residual`` es JSON estricto: ``"0"`` (PASS exacto), ``str`` del
    máximo delta finito (FAIL por mismatches), o ``None`` (estado no auditable con
    ``reconciliation_error`` o libro ilegible). ``accounting_status`` y
    ``accounting_failure_reason`` son claves extra que el evaluador ignora (su check
    usa sólo ``accounting_residual``); se mantienen para trazabilidad operacional.
    """

    accounting_residual: str | None
    accounting_status: str
    accounting_failure_reason: str | None
    recovery_integrity: str
    unexplained_market_gaps: int
    market_evidence_complete: str
    decision_context_coverage: float
    state_continuity: str
    metrics_history_days: int
    critical_errors: list[dict[str, Any]]
    certification_reports_complete: str
    kill_switch_tested: str
    daily_loss_tested: str
    fill_count: int
    closed_trade_count: int
    trade_count: int


def _dict_entries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [{str(k): v for k, v in item.items()} for item in value if isinstance(item, Mapping)]


def _string_list(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _previous_critical_errors(previous: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Errores críticos acumulados: los de `operational` en estado v2, si no legacy."""
    if previous.get("schema_version") == 2:
        operational = previous.get("operational")
        if isinstance(operational, Mapping):
            return _dict_entries(operational.get("critical_errors"))
    return _dict_entries(previous.get("critical_errors"))


def _market_regimes(previous: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _dict_entries(previous.get("market_regimes"))


def _collect_reports(previous: Mapping[str, Any], report_path: str | None) -> list[str]:
    """Reportes periódicos acumulados (dedup, orden estable) + el actual."""
    reports = _string_list(previous.get("periodic_reports"))
    if report_path and report_path not in reports:
        reports.append(report_path)
    return reports


def _report_date(report_path: str) -> str | None:
    """Fecha UTC (`YYYY-MM-DD`) del nombre de reporte `paper-YYYYMMDD-HHMMSS.md`."""
    match = re.search(r"^paper-(\d{4})(\d{2})(\d{2})-\d{6}\.md$", Path(report_path).name)
    if match is None:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _certification_reports_complete(heartbeats: Sequence[str], reports: Sequence[str]) -> str:
    """PASS si cada día con heartbeat confirmado tiene un reporte periódico.

    Los reportes llevan la fecha en el nombre (`paper-%Y%m%d-%H%M%S.md`); un día
    confirmado sin reporte fechado ⇒ FAIL. Sin heartbeats confirmados no hay día
    que exigir (vacuo PASS; la cobertura real la gatea `metrics_history_days`).
    """
    expected = {h for h in heartbeats if re.fullmatch(r"\d{4}-\d{2}-\d{2}", h) is not None}
    if not expected:
        return "PASS"
    found = {day for path in reports if (day := _report_date(path)) is not None}
    return "PASS" if expected.issubset(found) else "FAIL"


def _session_calendar_days(summary: PaperRunSummary) -> int:
    first = summary.first_timestamp_ms
    latest = summary.latest_timestamp_ms
    if first is None or latest is None:
        return 0
    return max(1, ((latest - first) // 86_400_000) + 1)


def _finite_decimal_str(value: Decimal) -> str | None:
    """str(Decimal) sólo si es finito; ``None`` para NaN/±Infinity (JSON estricto)."""
    return str(value) if value.is_finite() else None


def _sanitize_nonfinite(value: object) -> object:
    """Sustituye valores no-finitos por ``None`` (guardia JSON estricto).

    Ninguna escritura v2 puede contener ``float``/``Decimal`` NaN o ±Infinity en un
    campo numérico: el valor de origen no-finito se emite ``null`` según semántica,
    nunca la cadena ``"NaN"``. Recurre sobre dicts/lists.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, Mapping):
        return {str(key): _sanitize_nonfinite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_nonfinite(item) for item in value]
    return value


def _sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Aplica la guardia de finitud a la raíz del estado v2 (recursivo)."""
    return {str(key): _sanitize_nonfinite(value) for key, value in state.items()}


def build_certification_state_v2(
    *,
    previous: Mapping[str, Any],
    summary: PaperRunSummary,
    events: Sequence[PaperTradeEvent],
    candles: Sequence[Candle],
    heartbeat_ok: bool,
    today: str,
    safeguard_evidence: Mapping[str, Any],
    reconciliation: ReconciliationResult | None = None,
    reconciliation_error: str | None = None,
    artifact: RuntimeArtifact,
    now_ms: int,
    interval_ms: int,
    report_path: str | None,
) -> dict[str, Any]:
    """Compone el estado v2 canónico (productor real del paper-runner).

    Sin lookahead: todo evento/víela con `timestamp_ms > now_ms` se descarta.
    `frozen` es inmutable y NUNCA auto-ancla: si no hay un frozen previo compatible,
    la escritura produce NOT_STARTED (``certification_started_at`` null); el ancla
    del reloj se crea sólo con `start_certification` (Task 7). `current` se refresca
    con el artefacto de esta escritura y el ancla EN VIGOR del frozen (null si
    NOT_STARTED) para no inducir drift. `operational` se deriva de los kernels
    (Task 3), de `reconciliation` (Task 4b) y de la evidencia de safeguards
    (fail-closed). `accounting_book` sólo avanza con PASS exacto; con FAIL finito,
    `reconciliation_error` (p. ej. ``"missing_persisted_mark"``) o libro ilegible
    conserva el previo (nunca avanza con estado corrupto) y el residual es JSON
    estricto (``"0"`` / ``str`` del máximo delta finito / ``None``), sin NaN.
    """
    candles_scoped = [c for c in candles if c.timestamp_ms <= now_ms]
    events_scoped = [e for e in events if e.timestamp_ms <= now_ms]
    unique_candles = {c.timestamp_ms: c for c in candles_scoped}
    candles_sorted = [unique_candles[ts] for ts in sorted(unique_candles)]

    gaps = unexplained_gap_count(candles_sorted, interval_ms)
    fill_count, closed_trade_count, trade_count = fill_counts(events_scoped)

    heartbeats = add_metrics_heartbeat(previous, today, artifact_ok=heartbeat_ok)
    frozen = _resolve_frozen(previous, artifact)
    started_value = frozen.get("certification_started_at")
    started_at_iso = started_value if isinstance(started_value, str) else None
    current = _current_block(artifact, started_at_iso=started_at_iso)
    continuity = state_continuity(
        previous,
        application_version=artifact.application_version,
        session_id=summary.session_id,
    )

    errors = _previous_critical_errors(previous)
    periodic_reports = _collect_reports(previous, report_path)
    market_regimes = _market_regimes(previous)

    raw_book = previous.get("accounting_book")
    has_book = raw_book is not None
    book_illegible = has_book and (
        not isinstance(raw_book, Mapping) or BookState.from_dict(raw_book) is None
    )

    # Resolución contable fail-closed con JSON estricto (sin NaN/±Infinity):
    # el residual se emite como "0" (PASS), str(delta finito) (FAIL) o None (estado
    # no auditable); el libro nunca avanza con estado corrupto o no auditado.
    accounting_book: Mapping[str, Any] | None
    if book_illegible:
        accounting_residual: str | None = None
        accounting_status = "FAIL"
        accounting_failure_reason = "unparseable_accounting_book"
        errors.append({"message": "unparseable accounting_book", "explained": False})
        accounting_book = raw_book if isinstance(raw_book, Mapping) else None
    elif reconciliation_error is not None:
        accounting_residual = None
        accounting_status = "FAIL"
        accounting_failure_reason = reconciliation_error
        errors.append({"message": reconciliation_error, "explained": False})
        accounting_book = raw_book if isinstance(raw_book, Mapping) else None
    elif reconciliation is not None and reconciliation.status == "PASS":
        accounting_residual = "0"
        accounting_status = "PASS"
        accounting_failure_reason = None
        accounting_book = reconciliation.book.to_dict()
    elif reconciliation is not None:
        accounting_residual = _finite_decimal_str(reconciliation.accounting_residual)
        accounting_status = "FAIL"
        accounting_failure_reason = "accounting_mismatch"
        accounting_book = raw_book if isinstance(raw_book, Mapping) else None
    else:
        accounting_residual = None
        accounting_status = "FAIL"
        accounting_failure_reason = "accounting_unavailable"
        accounting_book = raw_book if isinstance(raw_book, Mapping) else None

    facts = OperationalFacts(
        accounting_residual=accounting_residual,
        accounting_status=accounting_status,
        accounting_failure_reason=accounting_failure_reason,
        recovery_integrity=recovery_integrity(errors),
        unexplained_market_gaps=gaps,
        market_evidence_complete=market_evidence_complete(gaps, candles_sorted, events_scoped),
        decision_context_coverage=decision_context_coverage(events_scoped),
        state_continuity=continuity,
        metrics_history_days=metrics_history_days(heartbeats),
        critical_errors=errors,
        certification_reports_complete=_certification_reports_complete(
            heartbeats, periodic_reports
        ),
        kill_switch_tested=(
            "PASS" if safeguard_passes(safeguard_evidence, "kill_switch", frozen) else "FAIL"
        ),
        daily_loss_tested=(
            "PASS" if safeguard_passes(safeguard_evidence, "daily_loss", frozen) else "FAIL"
        ),
        fill_count=fill_count,
        closed_trade_count=closed_trade_count,
        trade_count=trade_count,
    )

    return _sanitize_state(
        {
            "schema_version": 2,
            "session_id": summary.session_id,
            "session_started_at": _iso_utc_ms(session_started_at_ms(summary, now_ms)),
            "application_version": artifact.application_version,
            "frozen": frozen,
            "current": current,
            "operational": asdict(facts),
            "accounting_book": accounting_book,
            "metrics_heartbeats": heartbeats,
            "status": None,
            "invalidated_reason": None,
            # Claves legacy planas (compatibilidad de lectura con 0.1.x/evaluador).
            "strategy_version": summary.strategy_version,
            "strategy_hash": summary.strategy_hash,
            "active_strategy_hash": summary.strategy_hash,
            "calendar_days": _session_calendar_days(summary),
            "trade_count": summary.fills,
            "market_regimes": market_regimes,
            "periodic_reports": periodic_reports,
            "latest_equity": summary.latest_equity,
            "initial_equity": summary.initial_equity,
            "pnl_absolute": summary.pnl_absolute,
            "pnl_pct": summary.pnl_pct,
        }
    )


def _json_default(value: Any) -> str:
    """Serializa ``Decimal`` por ``str(value)`` (los estados v2 son JSON puros)."""
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def _serialize_v2(state: dict[str, Any]) -> str:
    return json.dumps(state, indent=2, sort_keys=True, default=_json_default) + "\n"


def write_certification_state_v2(state: dict[str, Any], state_path: Path) -> None:
    """Escritura crash-safe: tmp + fsync + `os.replace` atómico + fsync del dir.

    Un crash nunca deja un `certification-state.json` truncado que parezca
    válido: o existe el fichero anterior completo o el nuevo completo (replace
    atómico), nunca un estado intermedio bajo el nombre final.
    """
    serialized = _serialize_v2(state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_name(state_path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, state_path)
    try:
        dir_fd = os.open(state_path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
