"""market_candles: persistencia de velas paper-live con scope por sesión.

Revision ID: 0009_market_candles_paper_source
Revises: 0008_paper_trading_events
Create Date: 2026-09-08

La unicidad se separa por procedencia con índices parciales:
- ``download``:    UNIQUE (symbol, timeframe, timestamp_ms) WHERE source = 'download'
- ``paper-live``:  UNIQUE (session_id, symbol, timeframe, timestamp_ms) WHERE source = 'paper-live'

Esto permite múltiples sesiones paper sobre el mismo (symbol, timeframe, timestamp_ms)
sin colisionar con la descarga histórica (que no tiene session_id).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_market_candles_paper"
down_revision = "0008_paper_trading_events"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "market_candles",
        sa.Column("session_id", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "market_candles",
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "market_candles",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="download"),
    )
    op.add_column(
        "market_candles",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.drop_constraint("uq_market_candles_symbol_tf_ts", "market_candles", type_="unique")

    op.create_index(
        "uq_market_candles_download",
        "market_candles",
        ["symbol", "timeframe", "timestamp_ms"],
        unique=True,
        postgresql_where=sa.text("source = 'download'"),
    )
    op.create_index(
        "uq_market_candles_paper",
        "market_candles",
        ["session_id", "symbol", "timeframe", "timestamp_ms"],
        unique=True,
        postgresql_where=sa.text("source = 'paper-live'"),
    )
    op.create_check_constraint(
        "ck_market_candles_paper_session",
        "market_candles",
        "source <> 'paper-live' OR session_id IS NOT NULL",
    )
    op.create_index(
        "ix_market_candles_session_ts",
        "market_candles",
        ["session_id", "timestamp_ms"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_candles_session_ts", table_name="market_candles")
    op.drop_constraint("ck_market_candles_paper_session", "market_candles", type_="check")
    op.drop_index("uq_market_candles_paper", table_name="market_candles")
    op.drop_index("uq_market_candles_download", table_name="market_candles")

    op.create_unique_constraint(
        "uq_market_candles_symbol_tf_ts",
        "market_candles",
        ["symbol", "timeframe", "timestamp_ms"],
    )

    op.drop_column("market_candles", "created_at")
    op.drop_column("market_candles", "source")
    op.drop_column("market_candles", "confirmed")
    op.drop_column("market_candles", "session_id")
