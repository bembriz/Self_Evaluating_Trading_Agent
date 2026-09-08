"""paper_trade_events: decision_context JSONB versionado.

Revision ID: 0011_paper_events_decision_context
Revises: 0010_paper_events_idempotency
Create Date: 2026-09-08

Columna JSONB versionada que registra lo que vio la estrategia en T (indicadores,
regime, signal_reason) para auditabilidad y verificación no-lookahead.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_paper_events_context"
down_revision = "0010_paper_events_idempotency"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "paper_trade_events",
        sa.Column("decision_context", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_trade_events", "decision_context")
