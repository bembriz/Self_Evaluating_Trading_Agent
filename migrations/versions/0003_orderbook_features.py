"""orderbook_feature_windows

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "orderbook_feature_windows",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("window_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("window_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("best_bid", sa.Float(), nullable=True),
        sa.Column("best_ask", sa.Float(), nullable=True),
        sa.Column("spread", sa.Float(), nullable=True),
        sa.Column("spread_pct", sa.Float(), nullable=True),
        sa.Column("bid_depth", sa.Float(), nullable=False),
        sa.Column("ask_depth", sa.Float(), nullable=False),
        sa.Column("imbalance", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orderbook_feature_windows_symbol_start",
        "orderbook_feature_windows",
        ["symbol", "window_start_ms"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orderbook_feature_windows_symbol_start", table_name="orderbook_feature_windows"
    )
    op.drop_table("orderbook_feature_windows")
