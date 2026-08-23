"""market data: market_candles + dataset_manifests

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "market_candles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("turnover", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol", "timeframe", "timestamp_ms", name="uq_market_candles_symbol_tf_ts"
        ),
    )
    op.create_index(
        "ix_market_candles_symbol_tf_ts",
        "market_candles",
        ["symbol", "timeframe", "timestamp_ms"],
    )
    op.create_table(
        "dataset_manifests",
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("symbols", postgresql.JSONB(), nullable=False),
        sa.Column("timeframes", postgresql.JSONB(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_command", sa.Text(), nullable=False),
        sa.Column("files", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_version"),
    )


def downgrade() -> None:
    op.drop_table("dataset_manifests")
    op.drop_index("ix_market_candles_symbol_tf_ts", table_name="market_candles")
    op.drop_table("market_candles")
