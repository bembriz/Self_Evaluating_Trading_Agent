from pydantic import SecretStr
from pytest import MonkeyPatch

from settings import Settings, load_settings


def test_load_settings_tiene_defaults(monkeypatch: MonkeyPatch) -> None:
    for var in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
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


def test_llm_settings_defaults(monkeypatch: MonkeyPatch) -> None:
    for var in ("LLM_MODEL", "LLM_PROVIDER", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    s = load_settings()
    assert s.llm_provider == "deepseek"
    assert s.llm_model == "deepseek-v4-flash"
    assert s.llm_api_key.get_secret_value() == ""


def test_llm_settings_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("LLM_EXPERIMENT_BUDGET_USD", "7.5")
    s = load_settings()
    assert s.llm_model == "deepseek-v4-pro"
    assert s.llm_experiment_budget_usd == 7.5


def test_paper_runner_settings_defaults(monkeypatch: MonkeyPatch) -> None:
    for var in (
        "PAPER_DECISION_SOURCE",
        "PAPER_SYMBOLS",
        "PAPER_TIMEFRAME",
        "PAPER_REPORT_INTERVAL_HOURS",
        "PAPER_MAX_RUNTIME_DAYS",
    ):
        monkeypatch.delenv(var, raising=False)

    s = Settings()

    assert s.paper_decision_source == "baseline"
    assert s.paper_symbols == ["ETHUSDT"]
    assert s.paper_timeframe == "15m"
    assert s.paper_report_interval_hours == 24
    assert s.paper_max_runtime_days == 45


def test_paper_runner_safe_mode_env_overrides(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")

    s = Settings()

    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False


def test_paper_report_paths_defaults(monkeypatch: MonkeyPatch) -> None:
    for var in ("PAPER_REPORT_DIR", "PAPER_CERTIFICATION_STATE_PATH"):
        monkeypatch.delenv(var, raising=False)

    s = Settings()

    assert s.paper_report_dir == "reports/paper"
    assert s.paper_certification_state_path == "docs/phases/16/certification-state.json"


def test_paper_report_paths_env_override(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_REPORT_DIR", "custom/reports")
    monkeypatch.setenv("PAPER_CERTIFICATION_STATE_PATH", "custom/state.json")

    s = Settings()

    assert s.paper_report_dir == "custom/reports"
    assert s.paper_certification_state_path == "custom/state.json"
