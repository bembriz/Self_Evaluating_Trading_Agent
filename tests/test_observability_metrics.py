"""Tests RED — métricas de observabilidad del paper-runner (Opción A, Fase 16b).

Cubre las métricas nuevas/reutilizadas de `SetaMetrics`: ws_status, reconnect_total,
ws_errors_total (kind=ws), ws_stale_total, candles_processed y atr_ready.
"""

from __future__ import annotations

from infrastructure.observability.metrics import SetaMetrics


def test_new_metrics_render_prometheus_text() -> None:
    m = SetaMetrics()
    m.set_connected(True)
    m.inc_reconnect()
    m.inc_error("ws")
    m.inc_stale()
    m.inc_candle()
    m.set_atr_ready(True)

    text = m.render()

    assert "seta_ws_status 1.0" in text
    assert "seta_reconnects_total 1.0" in text
    assert 'seta_errors_total{kind="ws"} 1.0' in text
    assert "seta_ws_stale_total 1.0" in text
    assert "seta_candles_processed_total 1.0" in text
    assert "seta_atr_ready 1.0" in text


def test_ws_status_toggles_disconnected() -> None:
    m = SetaMetrics()
    m.set_connected(False)
    assert "seta_ws_status 0.0" in m.render()


def test_counters_accumulate() -> None:
    m = SetaMetrics()
    m.inc_candle()
    m.inc_candle()
    m.inc_reconnect()
    m.inc_stale()
    text = m.render()
    assert "seta_candles_processed_total 2.0" in text
    assert "seta_reconnects_total 1.0" in text
    assert "seta_ws_stale_total 1.0" in text


def test_atr_ready_gauge() -> None:
    m = SetaMetrics()
    m.set_atr_ready(False)
    assert "seta_atr_ready 0.0" in m.render()
    m.set_atr_ready(True)
    assert "seta_atr_ready 1.0" in m.render()
