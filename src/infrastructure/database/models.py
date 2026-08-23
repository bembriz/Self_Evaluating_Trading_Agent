"""Modelos ORM iniciales. El resto de entidades (PRD §55) llegan con su fase."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SystemState(Base):
    """Estado global del sistema (clave/valor) expuesto por /api/v1/system/state."""

    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), unique=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class MarketCandle(Base):
    """Vela OHLCV persistida (PRD §55 market_candles)."""

    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    turnover: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "timestamp_ms", name="uq_market_candles_symbol_tf_ts"
        ),
        Index("ix_market_candles_symbol_tf_ts", "symbol", "timeframe", "timestamp_ms"),
    )


class DatasetManifestRecord(Base):
    """Registro de manifest del dataset congelado (PRD §55 dataset_manifests)."""

    __tablename__ = "dataset_manifests"

    dataset_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    timeframes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    download_command: Mapped[str] = mapped_column(Text, nullable=False)
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OrderBookFeatureWindow(Base):
    """Features agregadas del order book (PRD §55 orderbook_feature_windows)."""

    __tablename__ = "orderbook_feature_windows"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    window_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid_depth: Mapped[float] = mapped_column(Float, nullable=False)
    ask_depth: Mapped[float] = mapped_column(Float, nullable=False)
    imbalance: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index("ix_orderbook_feature_windows_symbol_start", "symbol", "window_start_ms"),
    )
