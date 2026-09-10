"""paper_trade_events: idempotency key para recovery sin duplicados.

Revision ID: 0010_paper_trade_events_idempotency
Revises: 0009_market_candles_paper_source
Create Date: 2026-09-08

Un único evento lógico por vela (session_id, symbol, timeframe, timestamp_ms).
Permite ``ON CONFLICT DO NOTHING`` durante replay/backfill sin duplicar fills.
"""

from __future__ import annotations

from alembic import op

revision = "0010_paper_events_idempotency"
down_revision = "0009_market_candles_paper"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_paper_trade_events_session_symbol_tf_ts",
        "paper_trade_events",
        ["session_id", "symbol", "timeframe", "timestamp_ms"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_paper_trade_events_session_symbol_tf_ts",
        "paper_trade_events",
        type_="unique",
    )
