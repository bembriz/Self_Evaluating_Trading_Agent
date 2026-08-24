"""Tests del registro de métricas técnicas PRD §62."""

from __future__ import annotations

import pytest

from infrastructure.observability.metrics import SetaMetrics


@pytest.fixture
def metrics() -> SetaMetrics:
    return SetaMetrics()


def test_counter_and_gauge_render(metrics: SetaMetrics) -> None:
    metrics.inc_error("llm")
    metrics.inc_reconnect()
    metrics.set_ws_status(stale=False)
    text = metrics.render()
    assert 'seta_errors_total{kind="llm"} 1.0' in text
    assert "seta_reconnects_total 1.0" in text
    assert "seta_ws_stale 0.0" in text


def test_histogram_latencies_by_op(metrics: SetaMetrics) -> None:
    metrics.observe_latency("decision", 0.123)
    metrics.observe_latency("decision", 0.456)
    text = metrics.render()
    assert 'seta_latency_seconds_count{op="decision"} 2.0' in text
    assert 'seta_latency_seconds_sum{op="decision"}' in text


def test_llm_cost_gauge(metrics: SetaMetrics) -> None:
    metrics.set_llm_cost(1.25)
    assert "seta_llm_cost_usd 1.25" in metrics.render()


def test_render_is_prometheus_text_format(metrics: SetaMetrics) -> None:
    text = metrics.render()
    assert "# HELP" in text and "# TYPE" in text
