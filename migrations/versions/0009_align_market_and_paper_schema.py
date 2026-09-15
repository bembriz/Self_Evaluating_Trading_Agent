"""align market_candles + paper_trade_events with ORM models

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15

La cadena previa (0002/0008) quedó por detrás de los modelos ORM: faltaban
``market_candles.session_id/confirmed/source`` (con sus índices parciales y
check constraint) y ``paper_trade_events.decision_context`` (con su unique
constraint). Sin ellos, una DB creada con ``alembic upgrade head`` rechaza los
INSERT de los repositorios. Esta migración alinea el esquema sin tocar datos.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008_paper_trading_events"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- market_candles: columnas de procedencia ---
    op.add_column("market_candles", sa.Column("session_id", sa.String(length=96), nullable=True))
    op.add_column(
        "market_candles",
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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

    # El unique global de 0002 no distingue procedencia: los índices parciales
    # por ``source`` son la identidad real (download vs paper-live).
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
    op.create_index(
        "ix_market_candles_session_ts", "market_candles", ["session_id", "timestamp_ms"]
    )
    op.create_check_constraint(
        "ck_market_candles_paper_session",
        "market_candles",
        "source <> 'paper-live' OR session_id IS NOT NULL",
    )

    # --- paper_trade_events: contexto de decisión + identidad de sesión ---
    op.add_column(
        "paper_trade_events",
        sa.Column("decision_context", postgresql.JSONB(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_paper_trade_events_session_symbol_tf_ts",
        "paper_trade_events",
        ["session_id", "symbol", "timeframe", "timestamp_ms"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_paper_trade_events_session_symbol_tf_ts", "paper_trade_events", type_="unique"
    )
    op.drop_column("paper_trade_events", "decision_context")

    op.drop_constraint("ck_market_candles_paper_session", "market_candles", type_="check")
    op.drop_index("ix_market_candles_session_ts", table_name="market_candles")
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
