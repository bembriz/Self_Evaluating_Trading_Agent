"""Servidor /metrics minimal (stdlib) para el paper-runner (Fase 16b, Opción A).

Expone `SetaMetrics.render()` en 127.0.0.1 para validación local y futura
integración con Prometheus. Sin exposición pública del puerto (bind loopback).
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from infrastructure.observability.metrics import SetaMetrics


def start_metrics_server(
    metrics: SetaMetrics, *, host: str = "127.0.0.1", port: int = 9090
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/metrics":
                body = metrics.render().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args: object) -> None:
            pass  # silencioso: no ensuciar los logs del runner

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
