"""Adaptadores SQLAlchemy de los puertos de persistencia."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports.paper_trading import PaperTradeEvent
from domain.market.candle import Candle, Timeframe
from domain.market.dataset import CandleFileEntry, DatasetManifest
from domain.market.features import OrderBookFeatureSnapshot
from infrastructure.database.models import (
    DatasetManifestRecord,
    MarketCandle,
    OrderBookFeatureWindow,
    PaperTradeEventRecord,
    SystemState,
)


class SqlAlchemySystemStateRepository:
    """Implementación de SystemStateRepository sobre SQLAlchemy async."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> dict[str, Any] | None:
        row = await self._session.scalar(select(SystemState).where(SystemState.key == key))
        return row.value if row is not None else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        row = await self._session.scalar(select(SystemState).where(SystemState.key == key))
        if row is not None:
            row.value = value
        else:
            self._session.add(SystemState(key=key, value=value))
        await self._session.flush()

    async def ping(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
        except Exception:
            return False
        return True


class SqlAlchemyMarketCandleRepository:
    """Implementación de MarketCandleRepository con upsert idempotente."""

    BATCH_SIZE = 1000

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, symbol: str, timeframe: Timeframe, candles: list[Candle]) -> int:
        inserted = 0
        for offset in range(0, len(candles), self.BATCH_SIZE):
            batch = candles[offset : offset + self.BATCH_SIZE]
            rows = [
                {
                    "symbol": symbol,
                    "timeframe": timeframe.label,
                    "timestamp_ms": c.timestamp_ms,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "turnover": c.turnover,
                }
                for c in batch
            ]
            stmt = (
                pg_insert(MarketCandle)
                .values(rows)
                .on_conflict_do_nothing(
                    index_elements=["symbol", "timeframe", "timestamp_ms"],
                    index_where=text("source = 'download'"),
                )
                .returning(MarketCandle.id)
            )
            result = await self._session.execute(stmt)
            inserted += len(result.scalars().all())
        return inserted

    async def count(self, symbol: str, timeframe: Timeframe) -> int:
        stmt = (
            select(func.count())
            .select_from(MarketCandle)
            .where(MarketCandle.symbol == symbol, MarketCandle.timeframe == timeframe.label)
        )
        return int(await self._session.scalar(stmt) or 0)

    async def range(
        self, symbol: str, timeframe: Timeframe, start_ms: int, end_ms: int
    ) -> list[Candle]:
        stmt = (
            select(MarketCandle)
            .where(
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == timeframe.label,
                MarketCandle.timestamp_ms >= start_ms,
                MarketCandle.timestamp_ms <= end_ms,
            )
            .order_by(MarketCandle.timestamp_ms)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [self._to_domain(r) for r in rows]

    async def upsert_paper(
        self, session_id: str, symbol: str, timeframe: Timeframe, candles: list[Candle]
    ) -> int:
        inserted = 0
        for offset in range(0, len(candles), self.BATCH_SIZE):
            batch = candles[offset : offset + self.BATCH_SIZE]
            rows = [
                {
                    "session_id": session_id,
                    "symbol": symbol,
                    "timeframe": timeframe.label,
                    "timestamp_ms": c.timestamp_ms,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "turnover": c.turnover,
                    "source": "paper-live",
                    "confirmed": True,
                }
                for c in batch
            ]
            stmt = (
                pg_insert(MarketCandle)
                .values(rows)
                .on_conflict_do_nothing(
                    index_elements=["session_id", "symbol", "timeframe", "timestamp_ms"],
                    index_where=text("source = 'paper-live'"),
                )
                .returning(MarketCandle.id)
            )
            result = await self._session.execute(stmt)
            inserted += len(result.scalars().all())
        return inserted

    async def session_range(
        self,
        session_id: str,
        symbol: str,
        timeframe: Timeframe,
        start_ms: int,
        end_ms: int,
    ) -> list[Candle]:
        stmt = (
            select(MarketCandle)
            .where(
                MarketCandle.session_id == session_id,
                MarketCandle.symbol == symbol,
                MarketCandle.timeframe == timeframe.label,
                MarketCandle.source == "paper-live",
                MarketCandle.timestamp_ms >= start_ms,
                MarketCandle.timestamp_ms <= end_ms,
            )
            .order_by(MarketCandle.timestamp_ms)
        )
        rows = (await self._session.scalars(stmt)).all()
        return [self._to_domain(r) for r in rows]

    async def last_persisted_ms(
        self, session_id: str, symbol: str, timeframe: Timeframe
    ) -> int | None:
        stmt = select(func.max(MarketCandle.timestamp_ms)).where(
            MarketCandle.session_id == session_id,
            MarketCandle.symbol == symbol,
            MarketCandle.timeframe == timeframe.label,
            MarketCandle.source == "paper-live",
        )
        value = await self._session.scalar(stmt)
        return int(value) if value is not None else None

    @staticmethod
    def _to_domain(row: MarketCandle) -> Candle:
        return Candle(
            row.timestamp_ms,
            row.open,
            row.high,
            row.low,
            row.close,
            row.volume,
            row.turnover,
        )


class SqlAlchemyDatasetManifestRepository:
    """Implementación de DatasetManifestRepository (upsert por dataset_version)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, manifest: DatasetManifest) -> None:
        row = await self._session.get(DatasetManifestRecord, manifest.dataset_version)
        if row is None:
            row = DatasetManifestRecord(dataset_version=manifest.dataset_version)
            self._session.add(row)
        row.source = manifest.source
        row.schema_version = manifest.schema_version
        row.symbols = list(manifest.symbols)
        row.timeframes = list(manifest.timeframes)
        row.downloaded_at = datetime.fromisoformat(manifest.downloaded_at)
        row.download_command = manifest.download_command
        row.files = [f.to_dict() for f in manifest.files]
        await self._session.flush()

    async def get(self, version: str) -> DatasetManifest | None:
        row = await self._session.get(DatasetManifestRecord, version)
        if row is None:
            return None
        return DatasetManifest(
            dataset_version=row.dataset_version,
            source=row.source,
            schema_version=row.schema_version,
            symbols=tuple(row.symbols),
            timeframes=tuple(row.timeframes),
            downloaded_at=row.downloaded_at.isoformat(),
            download_command=row.download_command,
            files=tuple(CandleFileEntry.from_dict(f) for f in row.files),
        )


class SqlAlchemyOrderBookFeatureRepository:
    """Implementación de OrderBookFeatureRepository (insert de ventanas de features)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, feature: OrderBookFeatureSnapshot) -> None:
        self._session.add(
            OrderBookFeatureWindow(
                symbol=feature.symbol,
                window_start_ms=feature.window_start_ms,
                window_end_ms=feature.window_end_ms,
                best_bid=feature.best_bid,
                best_ask=feature.best_ask,
                spread=feature.spread,
                spread_pct=feature.spread_pct,
                bid_depth=feature.bid_depth,
                ask_depth=feature.ask_depth,
                imbalance=feature.imbalance,
            )
        )
        await self._session.flush()


class SqlAlchemyPaperTradeEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: PaperTradeEvent) -> None:
        stmt = (
            pg_insert(PaperTradeEventRecord)
            .values(
                session_id=event.session_id,
                strategy_version=event.strategy_version,
                strategy_hash=event.strategy_hash,
                decision_source=event.decision_source,
                symbol=event.symbol,
                timeframe=event.timeframe,
                timestamp_ms=event.timestamp_ms,
                action=event.action,
                filled=event.filled,
                risk_reason=event.risk_reason,
                exit_reason=event.exit_reason,
                exec_price=event.exec_price,
                quantity=event.quantity,
                fee=event.fee,
                slippage_cost=event.slippage_cost,
                equity=event.equity,
                kill_switch_active=event.kill_switch_active,
                decision_context=event.decision_context,
            )
            .on_conflict_do_nothing(
                index_elements=["session_id", "symbol", "timeframe", "timestamp_ms"]
            )
        )
        await self._session.execute(stmt)

    async def list_session(self, session_id: str) -> list[PaperTradeEvent]:
        rows = (
            await self._session.scalars(
                select(PaperTradeEventRecord)
                .where(PaperTradeEventRecord.session_id == session_id)
                .order_by(PaperTradeEventRecord.timestamp_ms, PaperTradeEventRecord.id)
            )
        ).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: PaperTradeEventRecord) -> PaperTradeEvent:
        return PaperTradeEvent(
            session_id=row.session_id,
            strategy_version=row.strategy_version,
            strategy_hash=row.strategy_hash,
            decision_source=row.decision_source,
            symbol=row.symbol,
            timeframe=row.timeframe,
            timestamp_ms=row.timestamp_ms,
            action=row.action,
            filled=row.filled,
            risk_reason=row.risk_reason,
            exit_reason=row.exit_reason,
            exec_price=row.exec_price,
            quantity=row.quantity,
            fee=row.fee,
            slippage_cost=row.slippage_cost,
            equity=row.equity,
            kill_switch_active=row.kill_switch_active,
            decision_context=row.decision_context,
        )
