from pydantic import SecretStr
from pytest import MonkeyPatch

from settings import Settings, load_settings


def test_load_settings_tiene_defaults() -> None:
    s = load_settings()
    assert s.app_name == "self-evaluating-trading-agent"
    assert s.trading_mode == "backtest"
    assert s.live_trading_enabled is False
    assert s.postgres_host == "localhost"
    assert s.postgres_port == 5433


def test_database_url_sin_password() -> None:
    s = Settings(
        postgres_host="db",
        postgres_port=5432,
        postgres_db="app",
        postgres_user="u",
        postgres_password=SecretStr(""),
    )
    assert s.database_url == "postgresql+psycopg://u@db:5432/app"


def test_database_url_con_password_codifica() -> None:
    s = Settings(
        postgres_host="db",
        postgres_port=5432,
        postgres_db="app",
        postgres_user="u",
        postgres_password=SecretStr("p@ss/w"),
    )
    assert s.database_url == "postgresql+psycopg://u:p%40ss%2Fw@db:5432/app"


def test_env_override_de_yaml(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    s = load_settings()
    assert s.postgres_port == 6543
