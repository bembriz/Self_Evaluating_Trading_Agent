"""Market Worker: stream de market data en tiempo real (PRD §63)."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from application.services.market_data_service import MarketDataConfig, MarketDataService
from domain.market.candle import Timeframe
from infrastructure.bybit.ws import BybitWebSocketClient
from infrastructure.database.repositories import (
    SqlAlchemyMarketCandleRepository,
    SqlAlchemyOrderBookFeatureRepository,
)
from infrastructure.database.session import build_session_factory, create_engine
from settings import Settings

MAX_RECONNECT_DELAY = 30.0


def _build_service(
    settings: Settings,
) -> tuple[MarketDataService, BybitWebSocketClient, AsyncEngine, AsyncSession]:
    engine = create_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    session = session_factory()
    stream = BybitWebSocketClient(url=settings.bybit_ws_url)
    service = MarketDataService(
        stream=stream,
        candle_repo=SqlAlchemyMarketCandleRepository(session),
        feature_repo=SqlAlchemyOrderBookFeatureRepository(session),
        config=MarketDataConfig(
            stale_timeout_seconds=settings.stale_timeout_seconds,
            feature_window_seconds=settings.feature_window_seconds,
            depth=settings.bybit_orderbook_depth,
        ),
        commit=session.commit,
    )
    return service, stream, engine, session


async def _session_run(
    settings: Settings,
    symbols: list[str],
    timeframes: list[Timeframe],
    health_holder: dict[str, str] | None = None,
) -> str:
    service, stream, engine, session = _build_service(settings)
    try:
        await service.run(symbols, timeframes)
        return str(service.health)
    finally:
        if health_holder is not None:
            health_holder["health"] = str(service.health)
        await session.close()
        await engine.dispose()
        await stream.close()


async def run_with_reconnect(
    run_once: Callable[[], Awaitable[str]],
    seconds: float,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> str:
    """Ejecuta `run_once` reconectando con backoff exponencial hasta `seconds`."""
    delay = 1.0
    deadline = asyncio.get_running_loop().time() + seconds
    health = "n/a"
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            health = await asyncio.wait_for(run_once(), timeout=remaining)
            break
        except TimeoutError:
            break
        except Exception as exc:  # noqa: BLE001 - reconexión genérica
            print(f"[market-worker] reconectando por {exc!r}", flush=True)
            await sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)
    return health


def market_worker(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(prog="market-worker")
    parser.add_argument("--symbols", nargs="+", default=["ETHUSDT", "BTCUSDT"])
    parser.add_argument("--timeframes", nargs="+", default=["15m", "1h", "4h"])
    parser.add_argument("--seconds", type=int, default=20)
    args = parser.parse_args(argv)
    settings = Settings()
    timeframes = [Timeframe.from_label(t) for t in args.timeframes]
    health_holder: dict[str, str] = {}

    async def session() -> str:
        return await _session_run(settings, args.symbols, timeframes, health_holder)

    health = asyncio.run(run_with_reconnect(session, args.seconds))
    if health == "n/a" and health_holder:
        health = health_holder["health"]
    print(f"[market-worker] health final: {health}")
    return 0
