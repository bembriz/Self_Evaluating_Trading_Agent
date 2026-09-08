import pytest

from domain.market.candle import Timeframe
from interfaces.cli.paper_runner import (
    MIN_RUNTIME_FOR_CERTIFICATION_DAYS,
    preflight_runtime,
    resolve_runtime_seconds,
    run_paper_runner,
)
from settings import Settings

SECONDS_PER_DAY = 24 * 60 * 60


def test_resolve_runtime_seconds_uses_max_days_when_cli_omitted() -> None:
    assert resolve_runtime_seconds(None, 45) == 45 * SECONDS_PER_DAY


def test_resolve_runtime_seconds_zero_days_means_unlimited() -> None:
    assert resolve_runtime_seconds(None, 0) is None


def test_resolve_runtime_seconds_cli_overrides_days() -> None:
    assert resolve_runtime_seconds(1, 45) == 1


def test_preflight_rejects_short_runtime_when_certifying() -> None:
    with pytest.raises(ValueError, match="runtime configurado insuficiente"):
        preflight_runtime(max_days=7, session_id="paper-baseline-15m-ethusdt-0.2.0")


def test_preflight_allows_minimum_runtime() -> None:
    preflight_runtime(max_days=45, session_id="paper-baseline-15m-ethusdt-0.2.0")


def test_preflight_allows_unlimited_runtime() -> None:
    preflight_runtime(max_days=0, session_id="paper-baseline-15m-ethusdt-0.2.0")


def test_preflight_skips_when_no_session() -> None:
    preflight_runtime(max_days=7, session_id=None)


def test_min_runtime_constant_is_forty_five_days() -> None:
    assert MIN_RUNTIME_FOR_CERTIFICATION_DAYS == 45


def test_run_paper_runner_zero_days_means_unlimited() -> None:
    captured: dict[str, object] = {}

    async def fake_run(
        settings: Settings, symbols: list[str], timeframe: Timeframe, seconds: int | None
    ) -> str:
        captured["seconds"] = seconds
        return "processed=0"

    settings = Settings(
        trading_mode="paper",
        live_trading_enabled=False,
        paper_max_runtime_days=0,
    )

    code = run_paper_runner(settings, argv=[], run=fake_run)

    assert code == 0
    assert captured["seconds"] is None
