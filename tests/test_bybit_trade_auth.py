"""Tests de órdenes (dominio puro) y del firmante HMAC de Bybit v5."""

import time

import pytest

from domain.trading.order import OrderRequest, OrderStatus, TrackedOrder
from infrastructure.bybit.auth import BybitSigner


def test_order_request_defaults_and_idempotency_key() -> None:
    req = OrderRequest(symbol="ETHUSDT", side="Buy", quantity=0.5)
    assert req.order_type == "Market"
    assert req.order_link_id.startswith("seta-") and len(req.order_link_id) == 20
    other = OrderRequest(symbol="ETHUSDT", side="Buy", quantity=0.5)
    assert other.order_link_id != req.order_link_id  # único por orden


def test_tracked_order_transitions() -> None:
    t = TrackedOrder(order_link_id="seta-abc", symbol="ETHUSDT", status=OrderStatus.NEW)
    t.update(status=OrderStatus.PARTIALLY_FILLED, cumulative_qty=0.2)
    assert t.status is OrderStatus.PARTIALLY_FILLED
    assert t.cumulative_qty == 0.2
    t.update(status=OrderStatus.FILLED, cumulative_qty=0.5)
    assert t.is_terminal() is True


def test_status_rejects_regression() -> None:
    t = TrackedOrder(order_link_id="x", symbol="E", status=OrderStatus.FILLED)
    with pytest.raises(ValueError, match="terminal"):
        t.update(status=OrderStatus.NEW, cumulative_qty=0.0)


def test_signer_known_vector() -> None:
    """Vector fijo precalculado: estabilidad y sensibilidad a cada campo."""
    signer = BybitSigner(api_key="K", api_secret="S", recv_window=5000)
    headers = signer.sign("/v5/order/create", payload='{"a":1}', timestamp_ms=1_700_000_000_000)
    assert headers["X-BAPI-API-KEY"] == "K"
    assert headers["X-BAPI-TIMESTAMP"] == "1_700_000_000_000".replace("_", "")
    assert headers["X-BAPI-RECV-WINDOW"] == "5000"
    # Firma determinista para los mismos inputs:
    again = signer.sign("/v5/order/create", payload='{"a":1}', timestamp_ms=1_700_000_000_000)
    assert again["X-BAPI-SIGN"] == headers["X-BAPI-SIGN"]
    # Sensible al secreto, path, payload y timestamp:
    import hashlib
    import hmac

    expected = hmac.new(
        b"S",
        b"1700000000000K5000" + b"/v5/order/create" + b'{"a":1}',
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-BAPI-SIGN"] == expected


def test_signer_get_query_string_payload() -> None:
    signer = BybitSigner(api_key="K", api_secret="S")
    h = signer.sign("/v5/order/realtime", payload="symbol=ETHUSDT&category=spot", timestamp_ms=123)
    import hashlib
    import hmac

    expected = hmac.new(
        b"S", b"123K10000" + b"/v5/order/realtime" + b"symbol=ETHUSDT&category=spot", hashlib.sha256
    ).hexdigest()
    assert h["X-BAPI-SIGN"] == expected


def test_signer_timestamp_defaults_to_now() -> None:
    signer = BybitSigner(api_key="K", api_secret="S")
    before = int(time.time() * 1000)
    h = signer.sign("/v5/market/time", payload="")
    after = int(time.time() * 1000)
    ts = int(h["X-BAPI-TIMESTAMP"])
    assert before <= ts <= after
