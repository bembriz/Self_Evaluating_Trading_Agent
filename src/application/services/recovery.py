"""Orquestación de recovery del paper-runner: restore por replay + backfill."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from application.ports.market_repositories import MarketCandleRepository
from application.ports.paper_trading import PaperTradeEventRepository
from application.ports.repositories import SystemStateRepository
from application.services.paper_runner import (
    PaperRunner,
    PaperRunnerConfig,
)
from domain.market.candle import Timeframe
from domain.risk.guards import KillSwitch, KillSwitchState

KILL_SWITCH_KEY = "kill_switch"
_MAX_TS = 2**63 - 1


async def restore_runner(
    *,
    config: PaperRunnerConfig,
    event_repo: PaperTradeEventRepository,
    candle_repo: MarketCandleRepository,
    system_state_repo: SystemStateRepository,
    symbol: str,
    timeframe: Timeframe,
) -> PaperRunner:
    """Reconstruye el runner desde velas + eventos persistidos (event replay).

    Carga el kill switch (estado humano no derivable) y replantea las velas
    verificando contra los eventos persistidos. Levanta ``RecoveryDivergenceError``
    o ``RecoveryGapError`` si el estado persistido no es determinista.
    """
    ks_data = await system_state_repo.get(KILL_SWITCH_KEY)
    kill_switch = KillSwitch(KillSwitchState.from_dict(ks_data)) if ks_data else KillSwitch()

    candles = await candle_repo.session_range(config.session_id, symbol, timeframe, 0, _MAX_TS)
    events = await event_repo.list_session(config.session_id)
    persisted = {(e.symbol, e.timeframe, e.timestamp_ms): e for e in events}

    runner = PaperRunner(
        config=config,
        event_repo=event_repo,
        candle_repo=candle_repo,
        kill_switch=kill_switch,
    )
    runner.replay([(symbol, timeframe.label, c) for c in candles], persisted)
    return runner


class BackfillFn(Protocol):
    async def __call__(self, *, cutoff_ms: int) -> None: ...


class SubscribeFn(Protocol):
    async def __call__(self) -> None: ...


async def recover_and_handoff(
    *,
    backfill: BackfillFn,
    subscribe: SubscribeFn,
    now_ms: Callable[[], int],
) -> None:
    """Secuencia de handoff sin ventana de pérdida:

    backfill hasta T0 → subscribe WS → segundo backfill hasta T1.

    El segundo backfill cierra la carrera de una vela que cierre entre el primer
    backfill y la suscripción WS. El solapamiento se resuelve por idempotencia
    (UPSERT + ON CONFLICT) en el pipeline único serializado.
    """
    await backfill(cutoff_ms=now_ms())
    await subscribe()
    await backfill(cutoff_ms=now_ms())
