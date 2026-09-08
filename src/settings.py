"""Configuración tipada por entorno: config/base.yaml + .env (PRD §58)."""

from __future__ import annotations

from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from version import __version__


class Settings(BaseSettings):
    """Parámetros de la aplicación. Precedencia: init > env/.env > YAML > defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        yaml_file="config/base.yaml",
        extra="ignore",
    )

    app_name: str = "self-evaluating-trading-agent"
    app_version: str = __version__
    trading_mode: str = "backtest"
    live_trading_enabled: bool = False
    paper_decision_source: str = "baseline"
    paper_symbols: list[str] = ["ETHUSDT"]
    paper_timeframe: str = "15m"
    paper_report_interval_hours: int = 24
    paper_max_runtime_days: int = 45
    paper_report_dir: str = "reports/paper"
    paper_certification_state_path: str = "docs/phases/16/certification-state.json"
    paper_session_id: str | None = None
    paper_metrics_host: str = "0.0.0.0"
    paper_metrics_port: int = 9090

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "trading_agent"
    postgres_user: str = "trading"
    postgres_password: SecretStr = SecretStr("")

    bybit_base_url: str = "https://api.bybit.com"
    bybit_request_timeout: float = 10.0
    dataset_dir: str = "datasets"

    bybit_ws_url: str = "wss://stream.bybit.com/v5/public/spot"
    bybit_orderbook_depth: int = 50
    stale_timeout_seconds: float = 10.0
    paper_stale_timeout_seconds: float = 120.0
    feature_window_seconds: int = 5

    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-v4-flash"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout: float = 30.0
    llm_temperature: float = 0.0
    llm_price_input_mtok: float = 0.27
    llm_price_output_mtok: float = 1.10
    llm_experiment_budget_usd: float = 5.0
    llm_monthly_budget_usd: float = 50.0
    prompts_dir: str = "prompts"

    otel_enabled: bool = False
    otel_endpoint: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    @property
    def database_url(self) -> str:
        """URL de conexión SQLAlchemy (driver psycopg3, soporta sync y async)."""
        password = self.postgres_password.get_secret_value()
        auth = (
            f"{self.postgres_user}:{quote_plus(password)}@"
            if password
            else f"{self.postgres_user}@"
        )
        return f"postgresql+psycopg://{auth}{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


def load_settings() -> Settings:
    """Construye Settings cargando config/base.yaml y aplicando .env/entorno."""
    return Settings()
