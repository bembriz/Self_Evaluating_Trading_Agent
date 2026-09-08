"""Verificación de la migración 0011 (decision_context JSONB) en el límite 0010↔0011."""

from __future__ import annotations

import psycopg
from alembic import command
from alembic.config import Config

from settings import Settings

_INSERT = """
INSERT INTO paper_trade_events (
    session_id, strategy_version, strategy_hash, decision_source, symbol,
    timeframe, timestamp_ms, action, filled, risk_reason, exit_reason,
    fee, slippage_cost, equity, kill_switch_active
) VALUES (
    'mig-test', 'v', 'h', 'baseline', 'ETHUSDT', '15m', 0, 'HOLD', false,
    '', '', 0.0, 0.0, 1000.0, false
)
"""


def test_migration_0011_roundtrip(migrated_db: str, test_settings: Settings) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", test_settings.database_url)

    # 0010 → 0011 → 0010 → 0011 (up/down roundtrip en el límite)
    command.downgrade(cfg, "0010_paper_events_idempotency")
    command.upgrade(cfg, "0011_paper_events_context")
    command.downgrade(cfg, "0010_paper_events_idempotency")
    command.upgrade(cfg, "0011_paper_events_context")

    plain_url = test_settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(plain_url, autocommit=True) as conn:
        # Fila existente sin decision_context sobrevive con NULL.
        conn.execute(_INSERT)
        null_row = conn.execute(
            "SELECT decision_context FROM paper_trade_events WHERE session_id='mig-test'"
        ).fetchone()
        assert null_row is not None
        assert null_row[0] is None

        # JSONB round-trip tras la migración.
        conn.execute(
            "UPDATE paper_trade_events SET decision_context = "
            '\'{"schema_version":1,"signal_reason":"warmup"}\'::jsonb '
            "WHERE session_id='mig-test'"
        )
        ctx_row = conn.execute(
            "SELECT decision_context FROM paper_trade_events WHERE session_id='mig-test'"
        ).fetchone()
        assert ctx_row is not None
        assert ctx_row[0] == {"schema_version": 1, "signal_reason": "warmup"}
