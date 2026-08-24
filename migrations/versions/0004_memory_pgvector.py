"""memory_items + reflections (pgvector)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0004"
down_revision = "0003"
branch_labels: str | None = None
depends_on: str | None = None

DIMENSION = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("outcome_timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False),
        sa.Column("mfe", sa.Float(), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("fees", sa.Float(), nullable=False),
        sa.Column("slippage", sa.Float(), nullable=False),
        sa.Column("reflection", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(length=64), nullable=False),
        sa.Column("experiment_id", sa.String(length=32), nullable=False),
        sa.Column("embedding_space", sa.String(length=128), nullable=False),
        sa.Column("embedding", Vector(DIMENSION), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_items_outcome_ts", "memory_items", ["outcome_timestamp_ms"])
    op.create_index("ix_memory_items_space", "memory_items", ["embedding_space"])
    op.create_index(
        "ix_memory_items_embedding_hnsw",
        "memory_items",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "reflections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("outcome_closed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("primary_error", sa.Text(), nullable=False),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("future_condition", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("reflections")
    op.drop_index("ix_memory_items_embedding_hnsw", table_name="memory_items")
    op.drop_index("ix_memory_items_space", table_name="memory_items")
    op.drop_index("ix_memory_items_outcome_ts", table_name="memory_items")
    op.drop_table("memory_items")
