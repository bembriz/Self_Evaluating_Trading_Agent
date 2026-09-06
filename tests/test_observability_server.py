"""Tests RED — servidor /metrics (stdlib, 127.0.0.1) del paper-runner."""

from __future__ import annotations

import urllib.request

from infrastructure.observability.metrics import SetaMetrics
from infrastructure.observability.server import start_metrics_server


def test_settings_default_bind_all_interfaces_and_port() -> None:
    from settings import Settings

    s = Settings()
    assert s.paper_metrics_host == "0.0.0.0"
    assert s.paper_metrics_port == 9090


def test_metrics_server_serves_prometheus_text() -> None:
    metrics = SetaMetrics()
    metrics.set_connected(True)
    metrics.inc_candle()

    # Bind 0.0.0.0 (interfaz prevista: accesible desde la red bridge Docker).
    # Se consulta vía 127.0.0.1, que también responde al estar en todas las interfaces.
    server = start_metrics_server(metrics, host="0.0.0.0", port=0)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as resp:
            body = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "seta_ws_status" in body
        assert "seta_candles_processed_total" in body
    finally:
        server.shutdown()
        server.server_close()
