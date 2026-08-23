from fastapi.testclient import TestClient


def test_health_liveness(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_con_db_disponible(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_system_state_fallback_a_settings(client: TestClient) -> None:
    r = client.get("/api/v1/system/state")
    assert r.status_code == 200
    body = r.json()
    assert body["trading_mode"] == "backtest"
    assert body["live_trading_enabled"] is False
    assert body["version"]
