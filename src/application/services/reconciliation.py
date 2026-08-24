"""Reconciliación de estados de órdenes local vs exchange (Fase 12).

Al reconectar (o periódicamente) se comparan las órdenes que el agente cree
abiertas contra lo que reporta el exchange: detecta fills/cancelaciones perdidos
y órdenes desconocidas para el estado local.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from domain.trading.order import OrderStatus
from infrastructure.bybit.trade_client import RemoteOrder


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """Diferencias entre el estado local y el remoto de órdenes abiertas."""

    unknown_remote: list[str] = field(default_factory=list)
    stale_local: list[str] = field(default_factory=list)
    status_diffs: list[tuple[str, OrderStatus, OrderStatus]] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        return not (self.unknown_remote or self.stale_local or self.status_diffs)


def reconcile(
    *,
    local: set[str],
    remote: list[RemoteOrder],
    local_status_of: Callable[[str], OrderStatus | None] | None = None,
) -> ReconciliationReport:
    """Compara order_link_ids locales vs órdenes abiertas remotas."""
    remote_by_id = {r.order_link_id: r for r in remote}

    unknown_remote = sorted(set(remote_by_id) - local)
    # Remotas en estado terminal no deben estar en 'abiertas': si aparecen aquí,
    # el exchange ya las cerró ⇒ local está desactualizado solo si las cree vivas.
    remote_open_ids = {
        rid for rid, r in remote_by_id.items() if r.status not in OrderStatus.terminal_states()
    }
    stale_local = sorted(local - remote_open_ids)

    status_diffs: list[tuple[str, OrderStatus, OrderStatus]] = []
    if local_status_of is not None:
        for rid in sorted(local & set(remote_by_id)):
            mine = local_status_of(rid)
            theirs = remote_by_id[rid].status
            if (
                mine is not None
                and mine is not theirs
                and theirs not in (OrderStatus.terminal_states())
            ):
                status_diffs.append((rid, mine, theirs))

    return ReconciliationReport(
        unknown_remote=unknown_remote,
        stale_local=stale_local,
        status_diffs=status_diffs,
    )
