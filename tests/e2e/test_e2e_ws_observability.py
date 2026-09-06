"""E2E — observabilidad WS del paper-runner (connect → disconnect → reconnect → métricas).

Cubre el gap crítico: estado y reconexiones de Bybit WebSocket (y stale/velas/ATR).
"""

from __future__ import annotations

import asyncio
import contextlib
import urllib.request
from pathlib import Path
from typing import Any

from application.ports.market_stream import WebSocketDisconnected
from application.services.paper_runner import PaperRunner, PaperRunnerConfig
from domain.market.candle import Timeframe
from domain.market.stream import KlineUpdate
from infrastructure.observability.metrics import SetaMetrics
from infrastructure.observability.server import start_metrics_server
from interfaces.cli.paper_runner import _run_loop


class _Repo:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def add(self, event: Any) -> None:
        self.events.append(event)

    async def list_session(self, session_id: str) -> list[Any]:
        return self.events


class _Stream:
    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)
        self.reconnect_calls = 0

    async def recv(self) -> Any:
        if self._events:
            item = self._events.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item
        await asyncio.sleep(0.02)
        return None


class _StallingStream:
    """Primera recv se cuelga (stale); luego responde rápido."""

    def __init__(self) -> None:
        self.calls = 0
        self.reconnect_calls = 0

    async def recv(self) -> Any:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(0.3)  # > stale_timeout (0.05)
        return None


def _kline(ts: int) -> KlineUpdate:
    return KlineUpdate(
        "ETHUSDT", Timeframe.M15, ts, 2000.0, 2000.0, 2000.0, 2000.0, 10.0, 1000.0, True
    )


def _runner(repo: _Repo) -> PaperRunner:
    cfg = PaperRunnerConfig(
        trading_mode="paper",
        live_trading_enabled=False,
        symbols=("ETHUSDT",),
        timeframe="15m",
        session_id="t",
        decision_source="baseline",
    )
    return PaperRunner(config=cfg, event_repo=repo)


async def test_e2e_ws_disconnect_reconnect_updates_metrics(tmp_path: Path) -> None:
    metrics = SetaMetrics()
    repo = _Repo()
    stream = _Stream([_kline(1_000), WebSocketDisconnected("drop"), _kline(2_000), _kline(3_000)])

    async def recover() -> None:
        stream.reconnect_calls += 1

    async def commit() -> None:
        pass

    await _run_loop(
        stream=stream,
        runner=_runner(repo),
        repo=repo,
        commit=commit,
        session_id="t",
        report_interval_seconds=3600,
        report_dir=tmp_path / "reports",
        state_path=tmp_path / "cert.json",
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
        recover=recover,
        metrics=metrics,
    )

    text = metrics.render()
    assert stream.reconnect_calls == 1
    assert "seta_reconnects_total 1.0" in text
    assert 'seta_errors_total{kind="ws"} 1.0' in text
    assert "seta_candles_processed_total 3.0" in text  # 3 velas confirmadas procesadas
    assert "seta_ws_status 1.0" in text  # reconectado al final


async def test_e2e_ws_stale_detection_marks_and_recovers(tmp_path: Path) -> None:
    metrics = SetaMetrics()
    repo = _Repo()
    stream = _StallingStream()

    async def recover() -> None:
        stream.reconnect_calls += 1

    async def commit() -> None:
        pass

    await _run_loop(
        stream=stream,
        runner=_runner(repo),
        repo=repo,
        commit=commit,
        session_id="t",
        report_interval_seconds=3600,
        report_dir=tmp_path / "reports",
        state_path=tmp_path / "cert.json",
        initial_equity=1000.0,
        deadline=asyncio.get_running_loop().time() + 1,
        recover=recover,
        metrics=metrics,
        stale_timeout_seconds=0.05,
    )

    text = metrics.render()
    assert stream.reconnect_calls == 1
    assert "seta_ws_stale_total 1.0" in text
    assert "seta_reconnects_total 1.0" in text


def _metric_value(port: int, name: str) -> str | None:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as resp:
        body: str = resp.read().decode("utf-8")
    for line in body.splitlines():
        if line.startswith(name + " "):
            return str(line.split()[1])
    return None


async def test_e2e_ws_status_sequence_via_metrics_endpoint(tmp_path: Path) -> None:
    """Consulta /metrics y verifica la secuencia real 1 -> 0 -> 1 de seta_ws_status."""
    metrics = SetaMetrics()
    server = start_metrics_server(metrics, host="127.0.0.1", port=0)
    port = server.server_address[1]
    try:

        class Stream:
            def __init__(self) -> None:
                self.disconnected = False
                self.recover_entered = asyncio.Event()
                self.release = asyncio.Event()

            async def recv(self) -> Any:
                if not self.disconnected:
                    self.disconnected = True
                    raise WebSocketDisconnected("drop")
                await asyncio.sleep(0.01)
                return None

        stream = Stream()

        async def recover() -> None:
            stream.recover_entered.set()
            await stream.release.wait()

        async def commit() -> None:
            pass

        # 1) conexión establecida (igual que _connect_subscribed en _run).
        metrics.set_connected(True)
        assert _metric_value(port, "seta_ws_status") == "1.0"

        task = asyncio.create_task(
            _run_loop(
                stream=stream,
                runner=_runner(_Repo()),
                repo=_Repo(),
                commit=commit,
                session_id="t",
                report_interval_seconds=3600,
                report_dir=tmp_path / "r",
                state_path=tmp_path / "c.json",
                initial_equity=1000.0,
                deadline=asyncio.get_running_loop().time() + 2.0,
                recover=recover,
                metrics=metrics,
                stale_timeout_seconds=0.0,
            )
        )

        # 2) desconexión: set_connected(False) ocurre antes de recover().
        await stream.recover_entered.wait()
        assert _metric_value(port, "seta_ws_status") == "0.0"
        assert "seta_reconnects_total" in metrics.render()
        assert 'seta_errors_total{kind="ws"} 1.0' in metrics.render()

        # 3) reconexión exitosa: set_connected(True).
        stream.release.set()
        await asyncio.sleep(0.05)
        assert _metric_value(port, "seta_ws_status") == "1.0"

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        server.shutdown()
        server.server_close()


async def test_e2e_atr_ready_gauge_flips_via_metrics_endpoint(tmp_path: Path) -> None:
    """atr_ready cambia 0 -> 1 al completar el warmup ATR (15 velas)."""
    metrics = SetaMetrics()
    server = start_metrics_server(metrics, host="127.0.0.1", port=0)
    port = server.server_address[1]
    try:
        candles = [_kline(1_000 + i * 900_000) for i in range(15)]

        class GatedCandleStream:
            def __init__(self) -> None:
                self._candles = list(candles)
                self.served = 0
                self.after_14 = asyncio.Event()
                self.release = asyncio.Event()

            async def recv(self) -> Any:
                if self.served == 14:
                    self.after_14.set()
                    await self.release.wait()
                if self.served < len(self._candles):
                    candle = self._candles[self.served]
                    self.served += 1
                    return candle
                await asyncio.sleep(0.01)
                return None

        stream = GatedCandleStream()

        async def commit() -> None:
            pass

        task = asyncio.create_task(
            _run_loop(
                stream=stream,
                runner=_runner(_Repo()),
                repo=_Repo(),
                commit=commit,
                session_id="t",
                report_interval_seconds=3600,
                report_dir=tmp_path / "r",
                state_path=tmp_path / "c.json",
                initial_equity=1000.0,
                deadline=asyncio.get_running_loop().time() + 3.0,
                recover=None,
                metrics=metrics,
                stale_timeout_seconds=0.0,
            )
        )

        # 14 velas procesadas: warmup ATR incompleto.
        await stream.after_14.wait()
        assert _metric_value(port, "seta_atr_ready") == "0.0"

        # 15ª vela: warmup completo.
        stream.release.set()
        await asyncio.sleep(0.05)
        assert _metric_value(port, "seta_atr_ready") == "1.0"

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    finally:
        server.shutdown()
        server.server_close()
