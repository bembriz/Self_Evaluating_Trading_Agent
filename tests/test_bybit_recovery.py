"""Tests de reconciliación de órdenes y recuperación de conexión (Fase 12)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from application.services.connection_supervisor import ConnectionSupervisor, SupervisorConfig
from application.services.reconciliation import ReconciliationReport, reconcile
from domain.trading.order import OrderStatus
from infrastructure.bybit.trade_client import RemoteOrder


def _remote(link_id: str, status: OrderStatus = OrderStatus.NEW) -> RemoteOrder:
    return RemoteOrder.tolerant(
        **{
            "orderLinkId": link_id,
            "orderId": f"oid-{link_id}",
            "status": status.value,
            "cumExecQty": "0",
            "avgPrice": "",
        }
    )


# ---------------------------------------------------------------- reconciliación


def test_reconciled_when_local_matches_remote() -> None:
    report = reconcile(local={"a"}, remote=[_remote("a")])
    assert isinstance(report, ReconciliationReport)
    assert report.unknown_remote == []
    assert report.stale_local == []
    assert report.is_consistent is True


def test_detects_orders_missing_locally() -> None:
    report = reconcile(local=set(), remote=[_remote("ghost")])
    assert report.unknown_remote == ["ghost"]
    assert report.is_consistent is False


def test_detects_stale_local_orders() -> None:
    # Local cree que 'a' sigue abierta; el exchange ya no la lista (fill/cancel).
    report = reconcile(local={"a", "b"}, remote=[_remote("b")])
    assert report.stale_local == ["a"]
    assert report.is_consistent is False


def test_status_mismatch_detected() -> None:
    local_states = {"a": OrderStatus.NEW}
    report = reconcile(
        local={"a"},
        remote=[_remote("a", OrderStatus.PARTIALLY_FILLED)],
        local_status_of=local_states.get,
    )
    assert len(report.status_diffs) == 1
    assert report.status_diffs[0] == ("a", OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)


def test_terminal_remote_not_flagged_unknown_if_known_locally() -> None:
    report = reconcile(local={"a", "z"}, remote=[_remote("z", OrderStatus.FILLED)])
    # 'z' no es desconocida (la conoce el local) pero sí desactualizada: cerró remota.
    assert report.unknown_remote == []
    assert set(report.stale_local) == {"a", "z"}


# ---------------------------------------------------------------- supervisor


async def test_supervisor_recovers_after_failures_and_calls_hook() -> None:
    attempts = {"n": 0}

    async def connect() -> None:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("down")

    reconnected = {"n": 0}

    async def on_reconnect() -> None:
        reconnected["n"] += 1

    cfg = SupervisorConfig(max_attempts=5, initial_backoff=0.01, max_backoff=0.02)
    supervisor = ConnectionSupervisor(cfg, connect=connect, on_reconnect=on_reconnect)
    await supervisor.run_once_until_connected()
    assert attempts["n"] == 3
    assert reconnected["n"] == 1  # hook tras la recuperación exitosa


async def test_supervisor_gives_up_after_max_attempts() -> None:
    async def connect() -> None:
        raise ConnectionError("down forever")

    cfg = SupervisorConfig(max_attempts=3, initial_backoff=0.001, max_backoff=0.002)
    supervisor = ConnectionSupervisor(cfg, connect=connect)
    with pytest.raises(ConnectionError):
        await supervisor.run_once_until_connected()
    assert supervisor.attempts == 3


def test_supervisor_backoff_is_bounded() -> None:
    cfg = SupervisorConfig(max_attempts=10, initial_backoff=0.5, max_backoff=1.0)
    assert cfg.delay_for(attempt=20) <= 1.0 + 1e-9


def test_remote_order_validation_error_on_bad_status() -> None:
    with pytest.raises(ValidationError):
        RemoteOrder.model_validate(
            {"orderLinkId": "x", "orderId": "o", "status": "WEIRD", "cumExecQty": ""}
        )
