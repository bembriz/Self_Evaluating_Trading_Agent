"""paper_trade_events

Revision ID: 0008_paper_trading_events
Revises: 0004
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_paper_trading_events"
down_revision = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "paper_trade_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=96), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("strategy_hash", sa.String(length=128), nullable=False),
        sa.Column("decision_source", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("filled", sa.Boolean(), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=False),
        sa.Column("exit_reason", sa.Text(), nullable=False),
        sa.Column("exec_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("fee", sa.Float(), nullable=False),
        sa.Column("slippage_cost", sa.Float(), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_trade_events_session_ts",
        "paper_trade_events",
        ["session_id", "timestamp_ms"],
    )
    op.create_index(
        "ix_paper_trade_events_symbol_tf_ts",
        "paper_trade_events",
        ["symbol", "timeframe", "timestamp_ms"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_trade_events_symbol_tf_ts", table_name="paper_trade_events")
    op.drop_index("ix_paper_trade_events_session_ts", table_name="paper_trade_events")
    op.drop_table("paper_trade_events")
