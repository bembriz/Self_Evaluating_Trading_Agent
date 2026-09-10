import importlib.util
import json
import sys
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.accounting_reconciliation import (
    latest_persisted_mark,
    reconcile_with_book,
)
from application.services.certification_snapshot import (
    FROZEN_VERSION_KEYS,
    RuntimeArtifact,
    _current_block,
    _iso_utc_ms,
    _resolve_frozen,
    add_metrics_heartbeat,
    build_certification_state_v2,
    certification_phase,
    decision_context_coverage,
    fill_counts,
    market_evidence_complete,
    metrics_history_days,
    missing_start_identity,
    pristine_session_conflict,
    recovery_integrity,
    runtime_artifact,
    safeguard_passes,
    session_context_conflict,
    slippage_and_fees,
    start_certification,
    state_continuity,
    unexplained_gap_count,
    write_certification_state_v2,
)
from application.services.paper_engine import PaperEngine
from application.services.paper_runner import PaperRunSummary, summarize_events
from domain.market.candle import Candle
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity

FROZEN_KEYS = {
    "git_commit",
    "application_version",
    "strategy_version",
    "risk_config_version",
    "docker_image_digest",
    "symbol",
    "timeframe",
    "initial_capital",
    "fees_slippage_config_version",
    "certification_started_at",
}


def _summary() -> PaperRunSummary:
    return PaperRunSummary(
        session_id="paper-baseline-ETHUSDT-15m",
        decision_source="baseline",
        strategy_version="baseline-v1",
        strategy_hash="h" * 64,
        symbol="ETHUSDT",
        timeframe="15m",
        first_timestamp_ms=1_700_000_000_000,
        latest_timestamp_ms=1_700_000_300_000,
        decisions={"BUY": 0, "SELL": 0, "HOLD": 1},
        fills=0,
        fees=0.0,
        slippage=0.0,
        latest_equity=1000.0,
        kill_switch_active=False,
        initial_equity=1000.0,
    )


def _artifact(now_ms: int) -> RuntimeArtifact:
    return runtime_artifact(
        summary=_summary(),
        app_version="0.2.0",
        git_commit="abc1234",
        docker_image_digest="sha256:deadbeef",
        risk_config=RiskConfig(),
        now_ms=now_ms,
    )


def _ev(
    action: str,
    *,
    filled: bool = True,
    ts: int = 1_700_000_000_000,
    dc: dict[str, Any] | None = None,
    exit_reason: str = "",
    fee: float = 0.0,
    slippage: float = 0.0,
) -> PaperTradeEvent:
    return PaperTradeEvent(
        session_id="s",
        strategy_version="v",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=ts,
        action=action,
        filled=filled,
        risk_reason="",
        exit_reason=exit_reason,
        exec_price=100.0,
        quantity=1.0,
        fee=fee,
        slippage_cost=slippage,
        equity=1000.0,
        kill_switch_active=False,
        decision_context=dc,
    )


def _candle(ts_ms: int) -> Candle:
    return Candle(
        timestamp_ms=ts_ms,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1.0,
        turnover=100.5,
    )


def test_iso_utc_ms_suffix_z() -> None:
    assert _iso_utc_ms(1_700_000_000_000).endswith("Z")


def test_frozen_and_current_carry_the_10_frozen_keys() -> None:
    artifact = _artifact(1_700_000_000_000)
    frozen = _resolve_frozen({"schema_version": 1, "trade_count": 0}, artifact)
    started_at = frozen["certification_started_at"]
    assert started_at is None
    current = _current_block(artifact, started_at_iso=started_at)
    assert set(frozen) == FROZEN_KEYS
    assert set(current) == FROZEN_KEYS
    assert current["certification_started_at"] == frozen["certification_started_at"]


def test_resolve_frozen_legacy_prev_does_not_anchor() -> None:
    """Legacy 0.1.x plano: NUNCA aporta ancla v2 (sin auto-ancla en la escritura)."""
    now_ms = 1_700_000_000_000
    frozen = _resolve_frozen({"schema_version": 1, "trade_count": 0}, _artifact(now_ms))
    assert frozen["certification_started_at"] is None


def test_resolve_frozen_keeps_previous_frozen_when_compatible() -> None:
    previous: dict[str, object] = {
        "schema_version": 2,
        "session_id": "paper-baseline-ETHUSDT-15m",
        "frozen": {
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "application_version": "0.2.0",
            "strategy_version": "baseline-v1",
            "certification_started_at": "2026-09-01T00:00:00Z",
        },
    }
    frozen = _resolve_frozen(previous, _artifact(1_700_000_300_000))
    assert frozen["certification_started_at"] == "2026-09-01T00:00:00Z"


def test_coverage_100_when_all_contexts_present() -> None:
    dc: dict[str, Any] = {"schema_version": 1, "signal_reason": "ema"}
    events = [_ev("BUY", dc=dc, ts=1), _ev("SELL", dc=dc, ts=2)]
    assert decision_context_coverage(events) == 100.0


def test_coverage_100_when_no_events() -> None:
    assert decision_context_coverage([]) == 100.0


def test_coverage_zero_when_context_missing() -> None:
    assert decision_context_coverage([_ev("BUY", dc=None)]) == 0.0


def test_coverage_partial_counts_events_with_full_context() -> None:
    dc: dict[str, Any] = {"schema_version": 1, "signal_reason": "ema"}
    events = [_ev("BUY", dc=dc), _ev("SELL", dc=None)]
    assert decision_context_coverage(events) == 50.0


def test_fill_counts_closed_trade_requires_exit_reason() -> None:
    fill, closed, trade = fill_counts([_ev("SELL", ts=1), _ev("SELL", ts=2, exit_reason="tp")])
    assert (fill, closed, trade) == (2, 1, 2)


def test_fill_counts_excludes_unfilled_orders() -> None:
    fill, closed, trade = fill_counts([_ev("SELL", filled=False), _ev("SELL", exit_reason="tp")])
    assert (fill, closed, trade) == (1, 1, 1)


def test_slippage_and_fees_sums_costs() -> None:
    events = [
        _ev("BUY", fee=1.5, slippage=0.25),
        _ev("SELL", fee=2.5, slippage=0.75, exit_reason="tp"),
    ]
    assert slippage_and_fees(events) == (1.0, 4.0)


def test_slippage_and_fees_zero_without_events() -> None:
    assert slippage_and_fees([]) == (0.0, 0.0)


def test_gap_count_counts_missing_bucket() -> None:
    candles = [_candle(0), _candle(1_800_000)]  # falta el bucket 900_000
    assert unexplained_gap_count(candles, interval_ms=900_000) == 1


def test_gap_count_counts_multiple_missing_buckets() -> None:
    candles = [_candle(0), _candle(2_700_000)]
    assert unexplained_gap_count(candles, interval_ms=900_000) == 2


def test_gap_count_zero_for_adjacent_candles() -> None:
    assert unexplained_gap_count([_candle(0), _candle(900_000)], interval_ms=900_000) == 0


def test_gap_count_zero_for_single_candle() -> None:
    assert unexplained_gap_count([_candle(0)], interval_ms=900_000) == 0


def test_market_evidence_complete_pass_when_candles_bound_events() -> None:
    candles = [_candle(0), _candle(1_800_000)]
    events = [_ev("BUY", ts=900_000), _ev("SELL", ts=1_200_000, exit_reason="tp")]
    assert market_evidence_complete(0, candles, events) == "PASS"


def test_market_evidence_complete_pass_without_events() -> None:
    assert market_evidence_complete(0, [_candle(0)], []) == "PASS"


def test_market_evidence_complete_fail_on_unexplained_gap() -> None:
    candles = [_candle(0), _candle(1_800_000)]
    events = [_ev("BUY", ts=900_000)]
    assert market_evidence_complete(1, candles, events) == "FAIL"


def test_market_evidence_complete_fail_when_event_outside_candles() -> None:
    candles = [_candle(0), _candle(900_000)]
    events = [_ev("BUY", ts=1_800_000)]
    assert market_evidence_complete(0, candles, events) == "FAIL"


def test_metrics_history_days_counts_distinct_dates() -> None:
    assert metrics_history_days(["2026-09-01", "2026-09-01", "2026-09-02"]) == 2


def test_metrics_history_days_zero_without_heartbeats() -> None:
    assert metrics_history_days([]) == 0


def test_add_metrics_heartbeat_appends_only_when_artifact_ok() -> None:
    prev: dict[str, Any] = {}
    assert add_metrics_heartbeat(prev, "2026-09-01", artifact_ok=False) == []
    heartbeats = add_metrics_heartbeat(prev, "2026-09-01", artifact_ok=True)
    assert heartbeats == ["2026-09-01"]
    assert prev == {}


def test_add_metrics_heartbeat_dedups_and_conserves_existing() -> None:
    prev: dict[str, Any] = {"metrics_heartbeats": ["2026-09-01"]}
    assert add_metrics_heartbeat(prev, "2026-09-01", artifact_ok=True) == ["2026-09-01"]
    assert add_metrics_heartbeat(prev, "2026-09-02", artifact_ok=True) == [
        "2026-09-01",
        "2026-09-02",
    ]


def test_state_continuity_pass_on_absent_previous() -> None:
    assert state_continuity({}, application_version="0.2.0", session_id="s") == "PASS"


def test_state_continuity_pass_on_legacy_schema() -> None:
    prev: dict[str, Any] = {
        "schema_version": 1,
        "application_version": "0.1.3",
        "session_id": "s",
    }
    assert state_continuity(prev, application_version="0.2.0", session_id="s") == "PASS"


def test_state_continuity_pass_when_version_and_session_match() -> None:
    prev: dict[str, Any] = {
        "schema_version": 2,
        "application_version": "0.2.0",
        "session_id": "s",
    }
    assert state_continuity(prev, application_version="0.2.0", session_id="s") == "PASS"


def test_state_continuity_fail_on_version_change() -> None:
    prev: dict[str, Any] = {
        "schema_version": 2,
        "application_version": "0.1.3",
        "session_id": "s",
    }
    assert state_continuity(prev, application_version="0.2.0", session_id="s") == "FAIL"


def test_state_continuity_fail_on_session_change() -> None:
    prev: dict[str, Any] = {
        "schema_version": 2,
        "application_version": "0.2.0",
        "session_id": "s",
    }
    assert state_continuity(prev, application_version="0.2.0", session_id="other") == "FAIL"


def test_recovery_integrity_pass_without_divergence_errors() -> None:
    errors: list[dict[str, Any]] = [
        {"message": "commit failure", "kind": "commit", "explained": False}
    ]
    assert recovery_integrity(errors) == "PASS"
    assert recovery_integrity([]) == "PASS"


def test_recovery_integrity_fail_on_divergence() -> None:
    errors: list[dict[str, Any]] = [
        {"message": "recovery diverged", "kind": "recovery_divergence", "explained": False}
    ]
    assert recovery_integrity(errors) == "FAIL"


# ---------------------------------------------------------------------------
# Task 5: composición del estado v2 + escritura (productor real)
# ---------------------------------------------------------------------------

_INTERVAL_MS = 900_000
_CAPITAL = 100_000.0
_NOW_MS = 1_700_000_000_000
_DAY0 = date(2026, 9, 1)

_SCEN_FLAT: list[tuple[float, Action]] = [
    (65000.0, Action.BUY),
    (65200.0, Action.HOLD),
    (65500.0, Action.SELL),
    (65000.0, Action.HOLD),
]

_KILL_SWITCH_STEPS = [
    "activate",
    "buy_rejected",
    "persist",
    "restart_still_active",
    "buy_still_rejected",
    "operator_reset",
]
_DAILY_LOSS_STEPS = [
    "daily_loss_exceeded",
    "buy_rejected",
    "sell_allowed",
    "restart_persists",
    "utc_rollover_reset",
]


def _load_evaluator() -> Any:
    """Carga el evaluador real del harness por ruta (paridad de contrato)."""
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "harness" / "scripts" / "paper_certification.py"
    spec = importlib.util.spec_from_file_location("paper_certification_evaluator", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _config() -> RiskConfig:
    return replace(
        RiskConfig(),
        capital=_CAPITAL,
        max_position_allocation=0.03,
        take_profit_r_multiple=100.0,
        trailing_atr_multiplier=100.0,
    )


def _decision(action: Action, ts: int) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts, action=action, confidence=0.8, intensity=Intensity.MEDIUM
    )


def _scen_candle(close: float, ts: int) -> Candle:
    return Candle(
        timestamp_ms=ts,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=10.0,
        turnover=close * 10.0,
    )


def _scenario_artifact(now_ms: int, config: RiskConfig) -> RuntimeArtifact:
    return runtime_artifact(
        summary=_summary(),
        app_version="0.2.0",
        git_commit="abc1234",
        docker_image_digest="sha256:deadbeef",
        risk_config=config,
        now_ms=now_ms,
    )


def _flat_scenario() -> tuple[list[PaperTradeEvent], list[Candle], RiskConfig]:
    """Replica paper_runner._process: BUY+SELL planos con el engine real.

    `equity` persistido = mark_to_market(close) después de procesar la vela, de
    modo que la reconciliación espejo del engine (Task 4) da PASS exacto.
    """
    config = _config()
    engine = PaperEngine(config=config)
    events: list[PaperTradeEvent] = []
    candles: list[Candle] = []
    start = 1_000_000_000
    for i, (close, action) in enumerate(_SCEN_FLAT):
        ts = start + i * _INTERVAL_MS
        paper_event = engine.on_price(
            decision=_decision(action, ts), price=close, atr=40.0, timestamp_ms=ts
        )
        equity = engine.mark_to_market(price=close)
        fill = paper_event.fill
        dc: dict[str, Any] = {"schema_version": 1, "signal_reason": "ema"}
        events.append(
            PaperTradeEvent(
                session_id=_summary().session_id,
                strategy_version="baseline-v1",
                strategy_hash="h" * 64,
                decision_source="baseline",
                symbol="ETHUSDT",
                timeframe="15m",
                timestamp_ms=ts,
                action=paper_event.action.name,
                filled=paper_event.filled,
                risk_reason=paper_event.risk_reason,
                exit_reason=paper_event.exit_reason,
                exec_price=fill.exec_price if fill is not None else None,
                quantity=fill.quantity if fill is not None else None,
                fee=fill.fee if fill is not None else 0.0,
                slippage_cost=fill.slippage_cost if fill is not None else 0.0,
                equity=equity,
                kill_switch_active=False,
                decision_context=dc,
            )
        )
        candles.append(_scen_candle(close, ts))
    return events, candles, config


def _buy_event(*, exec_price: float, quantity: float, fee: float, ts: int) -> PaperTradeEvent:
    dc: dict[str, Any] = {"schema_version": 1, "signal_reason": "ema"}
    return PaperTradeEvent(
        session_id=_summary().session_id,
        strategy_version="baseline-v1",
        strategy_hash="h" * 64,
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=ts,
        action="BUY",
        filled=True,
        risk_reason="",
        exit_reason="",
        exec_price=exec_price,
        quantity=quantity,
        fee=fee,
        slippage_cost=0.0,
        equity=0.0,
        kill_switch_active=False,
        decision_context=dc,
    )


def _open_good_scenario() -> tuple[list[PaperTradeEvent], list[Candle]]:
    """BUY 1.0@100 fee 0.1 con posición abierta y mark 110 (libro bueno)."""
    events = [_buy_event(exec_price=100.0, quantity=1.0, fee=0.1, ts=0)]
    candles = [_scen_candle(110.0, 0)]
    return events, candles


def _legacy_previous(*, heartbeats_days: int = 0) -> dict[str, Any]:
    """Estado legacy 0.1.x plano (runner actual) + heartbeats opcionales."""
    previous: dict[str, Any] = {
        "schema_version": 1,
        "session_id": "paper-baseline-ETHUSDT-15m",
        "strategy_version": "baseline-v1",
        "strategy_hash": "h" * 64,
        "active_strategy_hash": "h" * 64,
        "calendar_days": 1,
        "trade_count": 0,
        "market_regimes": [],
        "periodic_reports": [],
        "latest_equity": _CAPITAL,
        "initial_equity": _CAPITAL,
        "pnl_absolute": 0.0,
        "pnl_pct": 0.0,
    }
    if heartbeats_days:
        previous["metrics_heartbeats"] = [
            (_DAY0 + timedelta(days=i)).isoformat() for i in range(heartbeats_days)
        ]
    return previous


def _report_path(day: date) -> str:
    return f"/tmp/phase16c-reports/paper-{day:%Y%m%d}-120000.md"


def _safeguard_evidence(artifact: RuntimeArtifact) -> dict[str, Any]:
    artifact_match: dict[str, str] = {
        "git_commit": artifact.git_commit,
        "application_version": artifact.application_version,
        "docker_image_digest": artifact.docker_image_digest,
        "strategy_version": artifact.strategy_version,
        "risk_config_version": artifact.risk_config_version,
    }
    return {
        "kill_switch": {
            "type": "kill_switch",
            "status": "PASS",
            "at_iso": "2026-09-01T00:00:00Z",
            "steps": list(_KILL_SWITCH_STEPS),
            "artifact": dict(artifact_match),
        },
        "daily_loss": {
            "type": "daily_loss",
            "status": "PASS",
            "at_iso": "2026-09-01T00:00:00Z",
            "steps": list(_DAILY_LOSS_STEPS),
            "artifact": dict(artifact_match),
        },
    }


def _reconcile(
    events: list[PaperTradeEvent],
    candles: list[Candle],
    previous_book: dict[str, Any] | None,
    *,
    config: RiskConfig,
) -> Any:
    return reconcile_with_book(
        events,
        initial_capital=config.capital,
        mark_price=latest_persisted_mark(candles),
        previous_book=previous_book,
        interval_ms=_INTERVAL_MS,
    )


def _build_state(
    previous: dict[str, Any],
    *,
    events: list[PaperTradeEvent],
    candles: list[Candle],
    artifact: RuntimeArtifact,
    reconciliation: Any = None,
    reconciliation_error: str | None = None,
    now_ms: int,
    today: str,
    report_path: str | None = None,
    heartbeat_ok: bool = True,
) -> dict[str, Any]:
    return build_certification_state_v2(
        previous=previous,
        summary=_summary(),
        events=events,
        candles=candles,
        heartbeat_ok=heartbeat_ok,
        today=today,
        safeguard_evidence=_safeguard_evidence(artifact),
        reconciliation=reconciliation,
        reconciliation_error=reconciliation_error,
        artifact=artifact,
        now_ms=now_ms,
        interval_ms=_INTERVAL_MS,
        report_path=report_path,
    )


def _assert_strict_json(state: dict[str, Any]) -> None:
    """JSON estricto: ``allow_nan=False`` no lanza y no hay NaN/Infinity/-Infinity."""
    dump = json.dumps(state, allow_nan=False)
    for token in ("NaN", "Infinity", "-Infinity"):
        assert token not in dump


def _not_started_state() -> tuple[dict[str, Any], RuntimeArtifact]:
    """Estado v2 NOT_STARTED (escritura periódica sobre legacy) + artefacto."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS + 86_400_000, config)
    reconciliation = _reconcile(events, candles, None, config=config)
    state = _build_state(
        _legacy_previous(),
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 86_400_000,
        today=_DAY0.isoformat(),
    )
    assert certification_phase(state) == "NOT_STARTED"
    return state, artifact


def test_build_v2_pass_composes_canonical_state() -> None:
    """Legacy prev + fills + velas continuas + 30 heartbeats + safeguard PASS."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    previous = _legacy_previous(heartbeats_days=29)
    previous["periodic_reports"] = [_report_path(_DAY0 + timedelta(days=i)) for i in range(29)]
    today = (_DAY0 + timedelta(days=29)).isoformat()
    reconciliation = _reconcile(events, candles, None, config=config)
    state = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS,
        today=today,
        report_path=_report_path(_DAY0 + timedelta(days=29)),
    )

    assert state["schema_version"] == 2
    assert state["frozen"]["application_version"] == "0.2.0"
    assert state["operational"]["accounting_residual"] == "0"
    assert state["operational"]["accounting_status"] == "PASS"
    assert state["operational"]["accounting_failure_reason"] is None
    assert state["operational"]["metrics_history_days"] == 30
    assert state["operational"]["certification_reports_complete"] == "PASS"
    assert state["operational"]["kill_switch_tested"] == "PASS"
    assert state["operational"]["daily_loss_tested"] == "PASS"
    for legacy_key in (
        "strategy_version",
        "strategy_hash",
        "active_strategy_hash",
        "calendar_days",
        "trade_count",
        "market_regimes",
        "periodic_reports",
        "latest_equity",
        "initial_equity",
        "pnl_absolute",
        "pnl_pct",
    ):
        assert legacy_key in state
    assert state["accounting_book"] == reconciliation.book.to_dict()
    assert (
        state["current"]["certification_started_at"] == state["frozen"]["certification_started_at"]
    )
    assert state["frozen"]["certification_started_at"] is None
    _assert_strict_json(state)


def test_frozen_and_current_keys_match_real_evaluator_contract() -> None:
    """Paridad de contrato: las 10 claves del productor == evaluador real (por ruta)."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    reconciliation = _reconcile(events, candles, None, config=config)
    state = _build_state(
        _legacy_previous(),
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    evaluator = _load_evaluator()
    evaluator_keys = set(evaluator.FROZEN_VERSION_KEYS)
    assert set(FROZEN_VERSION_KEYS) == evaluator_keys
    assert set(state["frozen"]) == evaluator_keys
    assert set(state["current"]) == evaluator_keys


def test_periodic_write_before_start_keeps_clock_not_started() -> None:
    """(1/7) Escribir periódicamente antes de un START no inicia el reloj."""
    state, artifact = _not_started_state()
    assert state["frozen"]["certification_started_at"] is None
    assert state["current"]["certification_started_at"] is None
    assert certification_phase(state) == "NOT_STARTED"
    assert state["operational"]["accounting_residual"] == "0"


def test_explicit_start_creates_anchor() -> None:
    """(2/7) START explícito crea el anchor UTC == _iso_utc_ms(now) exacto."""
    state, artifact = _not_started_state()
    start_ms = _NOW_MS + 86_400_000
    started = start_certification(state, artifact, now_ms=start_ms)
    assert started["frozen"]["certification_started_at"] == _iso_utc_ms(start_ms)
    assert (
        started["current"]["certification_started_at"]
        == started["frozen"]["certification_started_at"]
    )
    assert certification_phase(started) == "RUNNING"


def test_second_start_while_running_does_not_reanchor() -> None:
    """(3/7) Dos START con now distinto sobre RUNNING ⇒ se conserva el primer anchor."""
    state, artifact = _not_started_state()
    start_ms = _NOW_MS + 86_400_000
    started = start_certification(state, artifact, now_ms=start_ms)
    anchor_first = started["frozen"]["certification_started_at"]
    again = start_certification(started, artifact, now_ms=start_ms + 86_400_000)
    assert again["frozen"]["certification_started_at"] == anchor_first
    assert certification_phase(again) == "RUNNING"


def test_restart_recompose_preserves_anchor() -> None:
    """(4/7) Estado RUNNING guardado y recompuesto tras restart ⇒ anchor byte-idéntico."""
    state, artifact = _not_started_state()
    started = start_certification(state, artifact, now_ms=_NOW_MS + 86_400_000)
    anchor = started["frozen"]["certification_started_at"]

    events, candles, config = _flat_scenario()
    restarted_artifact = _scenario_artifact(_NOW_MS + 2 * 86_400_000, config)
    reconciliation = _reconcile(events, candles, started["accounting_book"], config=config)
    recomposed = _build_state(
        started,
        events=events,
        candles=candles,
        artifact=restarted_artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 2 * 86_400_000,
        today=_DAY0.isoformat(),
    )
    assert recomposed["frozen"]["certification_started_at"] == anchor
    assert recomposed["frozen"] == started["frozen"]
    assert certification_phase(recomposed) == "RUNNING"


def test_invalidate_then_start_creates_new_anchor() -> None:
    """(5/7) INVALIDATED + nuevo START ⇒ anchor nuevo distinto del previo."""
    state, artifact = _not_started_state()
    started = start_certification(state, artifact, now_ms=_NOW_MS + 86_400_000)
    anchor_before = started["frozen"]["certification_started_at"]
    invalidated: dict[str, Any] = dict(started)
    invalidated["status"] = "INVALIDATED"
    invalidated["invalidated_reason"] = "drift strategy_version"
    assert certification_phase(invalidated) == "INVALIDATED"

    restarted = start_certification(invalidated, artifact, now_ms=_NOW_MS + 3 * 86_400_000)
    new_anchor = restarted["frozen"]["certification_started_at"]
    assert new_anchor == _iso_utc_ms(_NOW_MS + 3 * 86_400_000)
    assert new_anchor != anchor_before
    assert restarted["status"] is None
    assert restarted["invalidated_reason"] is None
    assert certification_phase(restarted) == "RUNNING"


def test_legacy_never_contributes_anchor_v2() -> None:
    """(6/7) Legacy 0.1.x ⇒ NOT_STARTED tras escritura v2; requiere START explícito."""
    events, candles, config = _flat_scenario()
    now_ms = _NOW_MS + 86_400_000
    artifact = _scenario_artifact(now_ms, config)
    previous = _legacy_previous()
    previous["last_report_at_ms"] = 1_700_000_500_000
    previous["previous_certification_started_at"] = "2026-08-01T00:00:00Z"
    reconciliation = _reconcile(events, candles, None, config=config)
    state = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=now_ms,
        today=_DAY0.isoformat(),
        report_path=_report_path(_DAY0),
    )
    assert state["frozen"]["certification_started_at"] is None
    assert state["frozen"]["certification_started_at"] != _iso_utc_ms(1_700_000_500_000)
    assert state["frozen"]["certification_started_at"] != "2026-08-01T00:00:00Z"
    assert certification_phase(state) == "NOT_STARTED"

    # Otra escritura periódica sobre el estado v2 NOT_STARTED tampoco ancla jamás.
    now2 = now_ms + 86_400_000
    reconciliation2 = _reconcile(events, candles, state["accounting_book"], config=config)
    state2 = _build_state(
        state,
        events=events,
        candles=candles,
        artifact=_scenario_artifact(now2, config),
        reconciliation=reconciliation2,
        now_ms=now2,
        today=_DAY0.isoformat(),
        report_path=_report_path(_DAY0),
    )
    assert state2["frozen"]["certification_started_at"] is None
    assert certification_phase(state2) == "NOT_STARTED"

    # El START explícito es el único camino a RUNNING.
    started = start_certification(state2, artifact, now_ms=_NOW_MS + 5 * 86_400_000)
    assert certification_phase(started) == "RUNNING"
    assert started["frozen"]["certification_started_at"] == _iso_utc_ms(_NOW_MS + 5 * 86_400_000)


def test_failed_reconciliation_keeps_previous_accounting_book() -> None:
    """Corrupción compensada: residual != 0 y el libro NO avanza."""
    events, candles = _open_good_scenario()
    config = _config()
    artifact = _scenario_artifact(_NOW_MS, config)
    previous = _legacy_previous(heartbeats_days=1)
    baseline = _reconcile(events, candles, None, config=config)
    good_state = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=baseline,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    good_book = good_state["accounting_book"]
    assert good_book == baseline.book.to_dict()

    corrupted = [_buy_event(exec_price=80.0, quantity=0.5, fee=5.1, ts=0)]
    reconciliation = reconcile_with_book(
        corrupted,
        initial_capital=config.capital,
        mark_price=110.0,
        previous_book=good_state["accounting_book"],
        interval_ms=_INTERVAL_MS,
    )
    assert reconciliation.status == "FAIL"
    failed_state = _build_state(
        good_state,
        events=corrupted,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + _INTERVAL_MS,
        today=_DAY0.isoformat(),
    )
    residual_value = failed_state["operational"]["accounting_residual"]
    assert isinstance(residual_value, str)
    assert residual_value != "0"
    assert Decimal(residual_value) == reconciliation.accounting_residual
    assert failed_state["operational"]["accounting_status"] == "FAIL"
    assert failed_state["operational"]["accounting_failure_reason"] == "accounting_mismatch"
    assert failed_state["accounting_book"] == good_book
    _assert_strict_json(failed_state)


def test_compatible_previous_frozen_preserved_byte_for_byte() -> None:
    """Dos llamadas con now_ms distinto conservan frozen idéntico (byte a byte)."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    previous = _legacy_previous(heartbeats_days=1)
    reconciliation1 = _reconcile(events, candles, None, config=config)
    state1 = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation1,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    now2 = _NOW_MS + 86_400_000 * 3
    reconciliation2 = _reconcile(events, candles, state1["accounting_book"], config=config)
    state2 = _build_state(
        state1,
        events=events,
        candles=candles,
        artifact=_scenario_artifact(now2, config),
        reconciliation=reconciliation2,
        now_ms=now2,
        today=_DAY0.isoformat(),
    )
    assert state2["frozen"] == state1["frozen"]
    assert json.dumps(state2["frozen"], sort_keys=True) == json.dumps(
        state1["frozen"], sort_keys=True
    )
    assert (
        state2["current"]["certification_started_at"]
        == state1["frozen"]["certification_started_at"]
    )


def _running_anchored_state() -> tuple[
    dict[str, Any], RiskConfig, list[PaperTradeEvent], list[Candle]
]:
    """Estado v2 RUNNING anclado (START explícito) listo para recibir drift."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    reconciliation = _reconcile(events, candles, None, config=config)
    state = _build_state(
        _legacy_previous(),
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    anchored = start_certification(state, artifact, now_ms=_NOW_MS)
    assert certification_phase(anchored) == "RUNNING"
    assert anchored["frozen"]["certification_started_at"] == _iso_utc_ms(_NOW_MS)
    return anchored, config, events, candles


def _drift_artifact(
    config: RiskConfig,
    *,
    strategy_version: str = "baseline-v1",
    app_version: str = "0.2.0",
    symbol: str = "ETHUSDT",
    timeframe: str = "15m",
) -> RuntimeArtifact:
    """Artefacto de una escritura cuya sesión (resumen) puede driftar."""
    drifted_summary = replace(
        _summary(), strategy_version=strategy_version, symbol=symbol, timeframe=timeframe
    )
    return runtime_artifact(
        summary=drifted_summary,
        app_version=app_version,
        git_commit="abc1234",
        docker_image_digest="sha256:deadbeef",
        risk_config=config,
        now_ms=_NOW_MS + 86_400_000,
    )


def test_running_drift_strategy_version_preserves_frozen_anchor() -> None:
    """(8/7) RUNNING + strategy_version distinta en la MISMA sesión ⇒ frozen intacto.

    La identidad que preserva el ancla es el contexto de sesión (symbol/timeframe),
    NO las claves de versión: un drift de strategy_version conserva el frozen
    anclado byte a byte y el evaluador emite ``frozen_versions`` FAIL sin re-anclar
    (corrección 16c.6 / Task 8 sobre el bug de pérdida silenciosa del reloj).
    """
    anchored, config, events, candles = _running_anchored_state()
    anchor_before = anchored["frozen"]["certification_started_at"]
    drifted = _drift_artifact(config, strategy_version="baseline-v2")
    reconciliation = _reconcile(events, candles, anchored["accounting_book"], config=config)
    state = _build_state(
        anchored,
        events=events,
        candles=candles,
        artifact=drifted,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 86_400_000,
        today=(_DAY0 + timedelta(days=1)).isoformat(),
        report_path=_report_path(_DAY0 + timedelta(days=1)),
    )
    assert state["frozen"] == anchored["frozen"]  # byte a byte
    assert state["frozen"]["certification_started_at"] == anchor_before
    assert state["frozen"]["strategy_version"] == "baseline-v1"
    assert state["current"]["strategy_version"] == "baseline-v2"
    assert state["frozen"] != state["current"]
    assert certification_phase(state) == "RUNNING"

    evaluator = _load_evaluator()
    report = evaluator.evaluate_certification(state, evaluated_at=_NOW_MS + 30 * 86_400_000)
    assert report.certification_age_days >= 30.0
    assert report.overall_status == "FAIL"
    assert any(reason.startswith("frozen_versions") for reason in report.failure_reasons)


def test_running_drift_application_version_preserves_frozen_anchor() -> None:
    """(9/7) RUNNING + application_version distinta ⇒ frozen intacto (anchor vivo)."""
    anchored, config, events, candles = _running_anchored_state()
    drifted = _drift_artifact(config, app_version="0.3.0")
    reconciliation = _reconcile(events, candles, anchored["accounting_book"], config=config)
    state = _build_state(
        anchored,
        events=events,
        candles=candles,
        artifact=drifted,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 86_400_000,
        today=(_DAY0 + timedelta(days=1)).isoformat(),
        report_path=_report_path(_DAY0 + timedelta(days=1)),
    )
    assert state["frozen"] == anchored["frozen"]
    assert state["current"]["application_version"] == "0.3.0"
    assert certification_phase(state) == "RUNNING"

    evaluator = _load_evaluator()
    report = evaluator.evaluate_certification(state, evaluated_at=_NOW_MS + 30 * 86_400_000)
    assert report.certification_age_days >= 30.0
    assert report.overall_status == "FAIL"
    assert any(reason.startswith("frozen_versions") for reason in report.failure_reasons)


def test_running_anchored_symbol_mismatch_preserves_frozen_and_fails_versions() -> None:
    """(8d/1) RUNNING anclado + artefacto con OTRO symbol ⇒ frozen intacto + frozen_versions FAIL.

    El ancla de certificación es un reloj de pared: una vez RUNNING, un artefacto que
    cambia de mercado NUNCA re-ancla ni pierde el frozen (regresión de la pérdida
    silenciosa del ancla). ``current`` refleja el drift (symbol distinto) y el
    evaluador emite ``frozen_versions`` FAIL con el ancla intacta y sin re-anclar.
    """
    anchored, config, events, candles = _running_anchored_state()
    anchor_before = anchored["frozen"]["certification_started_at"]
    other = _drift_artifact(config, symbol="BTCUSDT")
    reconciliation = _reconcile(events, candles, anchored["accounting_book"], config=config)
    state = _build_state(
        anchored,
        events=events,
        candles=candles,
        artifact=other,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 86_400_000,
        today=(_DAY0 + timedelta(days=1)).isoformat(),
        report_path=_report_path(_DAY0 + timedelta(days=1)),
    )
    assert state["frozen"] == anchored["frozen"]  # byte a byte, sin re-ancla
    assert state["frozen"]["certification_started_at"] == anchor_before
    assert state["frozen"]["symbol"] == "ETHUSDT"
    assert state["current"]["symbol"] == "BTCUSDT"
    assert state["frozen"] != state["current"]
    assert certification_phase(state) == "RUNNING"
    _assert_strict_json(state)

    evaluator = _load_evaluator()
    report = evaluator.evaluate_certification(state, evaluated_at=_NOW_MS + 30 * 86_400_000)
    assert report.certification_age_days >= 30.0
    assert report.overall_status == "FAIL"
    assert any(reason.startswith("frozen_versions") for reason in report.failure_reasons)


def test_running_anchored_timeframe_mismatch_preserves_frozen_and_fails_versions() -> None:
    """(8d/1b) RUNNING anclado + artefacto con OTRO timeframe ⇒ frozen intacto + FAIL.

    Igual que el mismatch de symbol: el contexto de sesión distinto jamás re-ancla
    mientras la certificación esté RUNNING; ``current`` refleja el timeframe driftado.
    """
    anchored, config, events, candles = _running_anchored_state()
    anchor_before = anchored["frozen"]["certification_started_at"]
    other = _drift_artifact(config, timeframe="5m")
    reconciliation = _reconcile(events, candles, anchored["accounting_book"], config=config)
    state = _build_state(
        anchored,
        events=events,
        candles=candles,
        artifact=other,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 86_400_000,
        today=(_DAY0 + timedelta(days=1)).isoformat(),
        report_path=_report_path(_DAY0 + timedelta(days=1)),
    )
    assert state["frozen"] == anchored["frozen"]  # byte a byte, sin re-ancla
    assert state["frozen"]["certification_started_at"] == anchor_before
    assert state["frozen"]["timeframe"] == "15m"
    assert state["current"]["timeframe"] == "5m"
    assert state["frozen"] != state["current"]
    assert certification_phase(state) == "RUNNING"
    _assert_strict_json(state)

    evaluator = _load_evaluator()
    report = evaluator.evaluate_certification(state, evaluated_at=_NOW_MS + 30 * 86_400_000)
    assert report.certification_age_days >= 30.0
    assert report.overall_status == "FAIL"
    assert any(reason.startswith("frozen_versions") for reason in report.failure_reasons)


def test_write_certification_state_v2_is_crash_safe(tmp_path: Path) -> None:
    """Sin fichero .tmp residual y contenido == serialización exacta."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    reconciliation = _reconcile(events, candles, None, config=config)
    state = _build_state(
        _legacy_previous(),
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    state_path = tmp_path / "certification-state.json"
    write_certification_state_v2(state, state_path)

    assert not state_path.with_name(state_path.name + ".tmp").exists()
    expected = json.dumps(state, indent=2, sort_keys=True, default=str) + "\n"
    assert state_path.read_text(encoding="utf-8") == expected


def test_present_but_illegible_accounting_book_fails_closed() -> None:
    """Libro presente pero inparseable ⇒ fail-closed (nunca baseline silencioso)."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    bad_book: dict[str, Any] = {"cash": "99899.9", "position_qty": "1.0"}
    previous = _legacy_previous(heartbeats_days=1)
    previous["accounting_book"] = bad_book
    # El espejo (Task 4b) trata el libro ilegible como carveout baseline...
    carveout = _reconcile(events, candles, bad_book, config=config)
    assert carveout.status == "PASS"
    # ...pero el productor debe override a fail-closed.
    state = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=carveout,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    residual_value = state["operational"]["accounting_residual"]
    assert residual_value is None
    assert state["operational"]["accounting_status"] == "FAIL"
    assert state["operational"]["accounting_failure_reason"] == "unparseable_accounting_book"
    messages = [e.get("message") for e in state["operational"]["critical_errors"]]
    assert "unparseable accounting_book" in messages
    assert all(
        e.get("explained") is False
        for e in state["operational"]["critical_errors"]
        if e.get("message") == "unparseable accounting_book"
    )
    assert state["accounting_book"] == bad_book
    _assert_strict_json(state)


def test_absent_accounting_book_is_baseline_pass() -> None:
    """Clave accounting_book ausente (primer ancla v2) ⇒ baseline PASS y libro nuevo."""
    events, candles, config = _flat_scenario()
    artifact = _scenario_artifact(_NOW_MS, config)
    reconciliation = _reconcile(events, candles, None, config=config)
    previous = _legacy_previous()
    assert "accounting_book" not in previous
    state = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    assert state["operational"]["accounting_residual"] == "0"
    assert not any(
        e.get("message") == "unparseable accounting_book"
        for e in state["operational"]["critical_errors"]
    )
    assert state["accounting_book"] == reconciliation.book.to_dict()


def test_missing_persisted_mark_error_fails_closed_without_nan() -> None:
    """reconciliation_error (caller/MissingMarkError) ⇒ residual None + FAIL, sin NaN."""
    events, candles = _open_good_scenario()
    config = _config()
    artifact = _scenario_artifact(_NOW_MS, config)
    previous = _legacy_previous(heartbeats_days=1)
    baseline = _reconcile(events, candles, None, config=config)
    good_state = _build_state(
        previous,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=baseline,
        now_ms=_NOW_MS,
        today=_DAY0.isoformat(),
    )
    good_book = good_state["accounting_book"]
    # El caller (Task 7) traduce MissingMarkError a reconciliation_error, nunca a NaN.
    state = _build_state(
        good_state,
        events=events,
        candles=candles,
        artifact=artifact,
        reconciliation=None,
        reconciliation_error="missing_persisted_mark",
        now_ms=_NOW_MS + _INTERVAL_MS,
        today=_DAY0.isoformat(),
    )
    residual_value = state["operational"]["accounting_residual"]
    assert residual_value is None
    assert state["operational"]["accounting_status"] == "FAIL"
    assert state["operational"]["accounting_failure_reason"] == "missing_persisted_mark"
    messages = [e.get("message") for e in state["operational"]["critical_errors"]]
    assert "missing_persisted_mark" in messages
    assert all(
        e.get("explained") is False
        for e in state["operational"]["critical_errors"]
        if e.get("message") == "missing_persisted_mark"
    )
    assert state["accounting_book"] == good_book
    _assert_strict_json(state)


def test_safeguard_passes_fail_closed() -> None:
    artifact = _scenario_artifact(_NOW_MS, _config())
    frozen = dict(_safeguard_evidence(artifact)["kill_switch"]["artifact"])
    exact = _safeguard_evidence(artifact)
    assert safeguard_passes(exact, "kill_switch", frozen)
    assert safeguard_passes(exact, "daily_loss", frozen)
    assert not safeguard_passes({}, "kill_switch", frozen)
    assert not safeguard_passes(exact, "kill_switch", {})

    def _with_artifact_mismatch(key: str) -> dict[str, Any]:
        changed = dict(exact)
        wrong_artifact = dict(frozen)
        wrong_artifact[key] = "drift-" + str(wrong_artifact[key])
        changed["kill_switch"] = {
            **changed["kill_switch"],
            "artifact": wrong_artifact,
        }
        return changed

    # Cualquier clave de artefacto distinta ⇒ fail-closed (fail-closed exacto).
    for drift_key in (
        "git_commit",
        "docker_image_digest",
        "strategy_version",
        "risk_config_version",
    ):
        assert not safeguard_passes(_with_artifact_mismatch(drift_key), "kill_switch", frozen)

    incomplete = dict(exact)
    incomplete["kill_switch"] = {
        **incomplete["kill_switch"],
        "steps": list(_KILL_SWITCH_STEPS[:-1]),
    }
    assert not safeguard_passes(incomplete, "kill_switch", frozen)

    incomplete_daily = dict(exact)
    incomplete_daily["daily_loss"] = {
        **incomplete_daily["daily_loss"],
        "steps": list(_DAILY_LOSS_STEPS[:-1]),
    }
    assert not safeguard_passes(incomplete_daily, "daily_loss", frozen)


# ---------------------------------------------------------------------------
# Task 8b: identidad al START (A), matcher safeguard type==kind (C)
# ---------------------------------------------------------------------------


def _pristine_summary() -> PaperRunSummary:
    """Resumen de sesión prístina (0 eventos): identidad vacía como en un arranque limpio."""
    return summarize_events([], initial_equity=_CAPITAL)


def _config_artifact(
    *,
    symbol: str = "ETHUSDT",
    timeframe: str = "15m",
    strategy_version: str = "baseline-v1",
    git_commit: str = "abc1234",
    summary: PaperRunSummary | None = None,
    now_ms: int = _NOW_MS,
) -> RuntimeArtifact:
    """Artefacto construido como el CLI: identidad = resumen persistido no vacío
    ELSE config (`symbol`/`timeframe`/`strategy_version` como defaults)."""
    return runtime_artifact(
        summary=summary if summary is not None else _pristine_summary(),
        app_version="0.2.0",
        git_commit=git_commit,
        docker_image_digest="sha256:deadbeef",
        risk_config=RiskConfig(),
        now_ms=now_ms,
        default_symbol=symbol,
        default_timeframe=timeframe,
        default_strategy_version=strategy_version,
    )


def test_pristine_session_identity_from_config_and_start_anchors() -> None:
    """(A1) Sesión prístina (0 eventos): identidad NUNCA vacía (viene de config) + START ancla."""
    artifact = _config_artifact(now_ms=_NOW_MS)
    assert artifact.symbol == "ETHUSDT"
    assert artifact.timeframe == "15m"
    assert artifact.strategy_version == "baseline-v1"
    assert missing_start_identity(artifact) == []

    start_ms = _NOW_MS + 86_400_000
    started = start_certification({}, artifact, now_ms=start_ms)
    assert certification_phase(started) == "RUNNING"
    assert started["frozen"]["certification_started_at"] == _iso_utc_ms(start_ms)
    assert started["frozen"]["symbol"] == "ETHUSDT"
    assert started["frozen"]["timeframe"] == "15m"
    assert started["frozen"]["strategy_version"] == "baseline-v1"
    assert started["current"]["symbol"] == "ETHUSDT"
    assert (
        started["current"]["certification_started_at"]
        == started["frozen"]["certification_started_at"]
    )


def test_restart_start_preserves_identity_and_anchor() -> None:
    """(A2) Restart (segundo START / recomposición misma identidad) ⇒ misma identidad + ancla."""
    artifact = _config_artifact(now_ms=_NOW_MS)
    first = start_certification({}, artifact, now_ms=_NOW_MS)
    anchor = first["frozen"]["certification_started_at"]
    assert anchor == _iso_utc_ms(_NOW_MS)

    second = start_certification(first, artifact, now_ms=_NOW_MS + 3 * 86_400_000)
    assert second["frozen"]["certification_started_at"] == anchor
    assert second["frozen"]["symbol"] == first["frozen"]["symbol"] == "ETHUSDT"
    assert second["frozen"]["timeframe"] == first["frozen"]["timeframe"] == "15m"
    assert (
        second["frozen"]["strategy_version"] == first["frozen"]["strategy_version"] == "baseline-v1"
    )


def test_runtime_artifact_rejects_persisted_identity_conflicting_with_config() -> None:
    """(A3a) Identidad persistida ≠ config ⇒ rechazo: NUNCA se resuelve silenciosamente.

    Resolución "persistido si existe, si no config" sólo rellena huecos: cuando el
    valor persistido (no vacío) contradice la config, elegir persistido etiquetaría
    mal el mercado que el runner realmente transmite y elegir config abandonaría la
    sesión persistida ⇒ ValueError (fail-fast), sin artefacto ni ancla.
    """
    persisted = replace(_summary(), symbol="BTCUSDT", timeframe="15m")
    with pytest.raises(ValueError, match="BTCUSDT"):
        runtime_artifact(
            summary=persisted,
            app_version="0.2.0",
            git_commit="abc1234",
            docker_image_digest="sha256:deadbeef",
            risk_config=RiskConfig(),
            now_ms=_NOW_MS,
            default_symbol="ETHUSDT",
            default_timeframe="15m",
            default_strategy_version="baseline-v1",
        )


def _not_started_state_with_session(symbol: str, timeframe: str) -> dict[str, Any]:
    """Estado v2 NOT_STARTED con un contexto de sesión previo (frozen, sin ancla)."""
    return {
        "schema_version": 2,
        "session_id": f"paper-baseline-{symbol.lower()}-{timeframe}",
        "application_version": "0.2.0",
        "status": None,
        "invalidated_reason": None,
        "frozen": {
            "git_commit": "abc1234",
            "application_version": "0.2.0",
            "strategy_version": "baseline-v1",
            "risk_config_version": RiskConfig().version,
            "docker_image_digest": "sha256:deadbeef",
            "symbol": symbol,
            "timeframe": timeframe,
            "initial_capital": _CAPITAL,
            "fees_slippage_config_version": "fees+slippage",
            "certification_started_at": None,
        },
        "current": {},
    }


def test_start_rejected_when_persisted_session_context_conflicts_with_config() -> None:
    """(A3b) Contexto de sesión persistido ≠ artefacto ⇒ START rechazado, sin ancla.

    Un estado previo (NOT_STARTED o RUNNING) con frozen de otra sesión jamás se
    re-ancla con una identidad inconsistente: el operador debe invalidar/archivar
    primero (upgrade intencional) antes de iniciar una certificación distinta.
    """
    previous = _not_started_state_with_session("ETHUSDT", "15m")
    artifact = _config_artifact(symbol="BTCUSDT", timeframe="15m", now_ms=_NOW_MS)

    assert session_context_conflict(previous, artifact) is not None
    with pytest.raises(ValueError, match="START rejected"):
        start_certification(previous, artifact, now_ms=_NOW_MS)
    assert previous["frozen"]["certification_started_at"] is None
    assert certification_phase(previous) == "NOT_STARTED"


def test_start_rejected_when_mandatory_identity_field_missing() -> None:
    """(A4) Campo obligatorio vacío (git_commit) ⇒ START rechazado: sin anchor, NOT_STARTED."""
    artifact = replace(_config_artifact(now_ms=_NOW_MS), git_commit="")
    assert missing_start_identity(artifact) == ["git_commit"]

    previous = _not_started_state_with_session("ETHUSDT", "15m")
    with pytest.raises(ValueError, match="git_commit"):
        start_certification(previous, artifact, now_ms=_NOW_MS)
    assert previous["frozen"]["certification_started_at"] is None
    assert certification_phase(previous) == "NOT_STARTED"


def test_start_over_running_context_mismatch_rejected_without_reanchor() -> None:
    """(8d/4) RUNNING anclado + contexto de sesión distinto ⇒ START rechazado, ancla intacta.

    Una certificación RUNNING JAMÁS se re-ancla (ni con identidad distinta): el
    rechazo fail-closed de ``session_context_conflict`` deja el estado previo intacto
    (mismo frozen y mismo ``certification_started_at``, fase RUNNING).
    """
    anchored, config, _events, _candles = _running_anchored_state()
    frozen_before = dict(anchored["frozen"])
    anchor_before = anchored["frozen"]["certification_started_at"]
    other = _drift_artifact(config, symbol="BTCUSDT")

    with pytest.raises(ValueError, match="START rejected"):
        start_certification(anchored, other, now_ms=_NOW_MS + 10 * 86_400_000)

    assert anchored["frozen"] == frozen_before
    assert anchored["frozen"]["certification_started_at"] == anchor_before
    assert certification_phase(anchored) == "RUNNING"


def test_start_pristine_config_identity_complete_envelope_never_empty() -> None:
    """(8d/3) START prístino con config válida ⇒ envelope v2 COMPLETO y frozen nunca vacío."""
    artifact = _config_artifact(now_ms=_NOW_MS)
    assert missing_start_identity(artifact) == []

    started = start_certification({}, artifact, now_ms=_NOW_MS)
    assert started["schema_version"] == 2
    for key in ("symbol", "timeframe", "strategy_version"):
        value = started["frozen"][key]
        assert isinstance(value, str) and value.strip(), f"frozen.{key} vacío"
    assert started["frozen"]["symbol"] == "ETHUSDT"
    assert started["frozen"]["timeframe"] == "15m"
    assert started["frozen"]["strategy_version"] == "baseline-v1"
    assert started["frozen"]["certification_started_at"] == _iso_utc_ms(_NOW_MS)
    assert certification_phase(started) == "RUNNING"
    _assert_strict_json(started)


def test_safeguard_passes_false_when_entry_type_mismatches_kind() -> None:
    """(C) El matcher exige entry['type'] == expected_kind (fail-closed)."""
    artifact = _scenario_artifact(_NOW_MS, _config())
    frozen = dict(_safeguard_evidence(artifact)["kill_switch"]["artifact"])
    exact = _safeguard_evidence(artifact)

    mismatched = dict(exact)
    mismatched["kill_switch"] = {**exact["kill_switch"], "type": "daily_loss"}
    assert not safeguard_passes(mismatched, "kill_switch", frozen)

    missing_type = dict(exact)
    missing_type["daily_loss"] = {k: v for k, v in exact["daily_loss"].items() if k != "type"}
    assert not safeguard_passes(missing_type, "daily_loss", frozen)

    assert safeguard_passes(exact, "kill_switch", frozen)
    assert safeguard_passes(exact, "daily_loss", frozen)


# ---------------------------------------------------------------------------
# Task 8c / F1: start_certification emite un envelope v2 COMPLETO (schema 2)
# ---------------------------------------------------------------------------


def test_start_absent_state_emits_complete_v2_envelope() -> None:
    """(F1) START sin estado previo (fichero ausente / {}) ⇒ doc v2 completo.

    Sin heurística {frozen,current}⇒v2: el envelope lleva `schema_version: 2`,
    session_id/session_started_at no vacíos, frozen+current con las 10 claves,
    operational presente, accounting_book presente (None) y status/invalidación
    limpias. Es el camino de deploy fresco que antes quedaba reclasificado legacy.
    """
    artifact = _config_artifact(now_ms=_NOW_MS)
    started = start_certification({}, artifact, now_ms=_NOW_MS)

    assert started["schema_version"] == 2
    assert isinstance(started["session_id"], str) and started["session_id"]
    assert started["session_started_at"] == _iso_utc_ms(_NOW_MS)
    # Simetría top-level con el productor periódico (Task 8c/F1 follow-up):
    # `state_continuity` compara `previous.application_version` (schema 2) ⇒ la
    # identidad top-level debe estar desde el primer doc para no emitir FAIL
    # espurio en la primera escritura periódica.
    assert started["application_version"] == artifact.application_version
    assert started["strategy_version"] == artifact.strategy_version
    assert started["strategy_hash"] == artifact.strategy_hash
    assert started["active_strategy_hash"] == artifact.strategy_hash
    assert set(started["frozen"]) == FROZEN_KEYS
    assert set(started["current"]) == FROZEN_KEYS
    assert started["frozen"]["certification_started_at"] == _iso_utc_ms(_NOW_MS)
    assert (
        started["current"]["certification_started_at"]
        == started["frozen"]["certification_started_at"]
    )
    assert isinstance(started["operational"], dict)
    assert started["accounting_book"] is None
    assert started["status"] is None
    assert started["invalidated_reason"] is None
    assert certification_phase(started) == "RUNNING"
    _assert_strict_json(started)


def test_first_periodic_write_over_fresh_start_envelope_state_continuity_pass() -> None:
    """(F1 follow-up) START sobre fichero ausente + 1ª escritura periódica real.

    El envelope de START lleva las claves de identidad top-level del productor
    periódico (`application_version`, strategy_*) ⇒ la primera escritura
    periódica (productor real) da `state_continuity == "PASS"` sin FAIL espurio.
    """
    artifact = _artifact(_NOW_MS)
    started = start_certification({}, artifact, now_ms=_NOW_MS)
    assert started["application_version"] == artifact.application_version

    events, candles, config = _flat_scenario()
    periodic_artifact = _scenario_artifact(_NOW_MS + 86_400_000, config)
    reconciliation = _reconcile(events, candles, started["accounting_book"], config=config)
    state = _build_state(
        started,
        events=events,
        candles=candles,
        artifact=periodic_artifact,
        reconciliation=reconciliation,
        now_ms=_NOW_MS + 86_400_000,
        today=_DAY0.isoformat(),
    )
    assert state["schema_version"] == 2
    assert certification_phase(state) == "RUNNING"
    assert (
        state["frozen"]["certification_started_at"] == started["frozen"]["certification_started_at"]
    )
    assert state["operational"]["state_continuity"] == "PASS"
    assert state["operational"]["accounting_status"] == "PASS"
    assert state["application_version"] == artifact.application_version
    _assert_strict_json(state)


def test_start_over_not_started_periodic_preserves_session_and_book() -> None:
    """(F1) START sobre NOT_STARTED periódico conserva session/start/book reales."""
    state, artifact = _not_started_state()  # periodic v2 con accounting_book baseline
    assert state["session_id"]
    assert state["session_started_at"]
    book = state["accounting_book"]
    assert book is not None
    start_ms = _NOW_MS + 86_400_000
    started = start_certification(state, artifact, now_ms=start_ms)

    assert started["schema_version"] == 2
    assert started["session_id"] == state["session_id"]
    assert started["session_started_at"] == state["session_started_at"]
    assert started["accounting_book"] == book  # preserva el checkpoint previo
    assert isinstance(started["operational"], dict)
    assert started["frozen"]["certification_started_at"] == _iso_utc_ms(start_ms)
    assert started["status"] is None
    assert certification_phase(started) == "RUNNING"


def test_start_invalidated_emits_complete_fresh_v2_envelope() -> None:
    """(F1) INVALIDATED + nuevo START ⇒ envelope v2 fresco y completo."""
    artifact = _config_artifact(now_ms=_NOW_MS)
    started = start_certification({}, artifact, now_ms=_NOW_MS)
    invalidated: dict[str, Any] = dict(started)
    invalidated["status"] = "INVALIDATED"
    invalidated["invalidated_reason"] = "operator"

    restarted = start_certification(invalidated, artifact, now_ms=_NOW_MS + 86_400_000)
    assert restarted["schema_version"] == 2
    assert restarted["session_id"] == started["session_id"]
    assert restarted["accounting_book"] == started["accounting_book"]
    assert isinstance(restarted["operational"], dict)
    assert restarted["status"] is None
    assert restarted["invalidated_reason"] is None
    assert restarted["frozen"]["certification_started_at"] == _iso_utc_ms(_NOW_MS + 86_400_000)
    assert certification_phase(restarted) == "RUNNING"
    _assert_strict_json(restarted)


def test_start_running_noop_keeps_full_v2_envelope() -> None:
    """(F1) RUNNING + segundo START ⇒ no-op: el envelope v2 se conserva intacto."""
    artifact = _config_artifact(now_ms=_NOW_MS)
    started = start_certification({}, artifact, now_ms=_NOW_MS)
    again = start_certification(started, artifact, now_ms=_NOW_MS + 86_400_000)
    assert again["schema_version"] == 2
    assert again["session_id"] == started["session_id"]
    assert (
        again["frozen"]["certification_started_at"] == started["frozen"]["certification_started_at"]
    )
    assert again == started  # no-op byte a byte


def test_start_legacy_flat_state_upgrades_to_v2_envelope() -> None:
    """(F1) START sobre legacy 0.1.x plano ⇒ envelope v2 (sin perder claves planas).

    El operador que inicia una certificación sobre un fichero legacy produce un
    doc `schema_version: 2` RUNNING; las claves legacy planas del dict previo se
    conservan para compatibilidad de lectura.
    """
    previous = _legacy_previous(heartbeats_days=3)
    artifact = _config_artifact(now_ms=_NOW_MS)
    started = start_certification(previous, artifact, now_ms=_NOW_MS)

    assert started["schema_version"] == 2
    assert started["strategy_version"] == "baseline-v1"  # clave plana conservada
    assert started["calendar_days"] == 1
    assert started["session_id"]
    assert started["session_started_at"] == _iso_utc_ms(_NOW_MS)
    assert started["accounting_book"] is None
    assert set(started["frozen"]) == FROZEN_KEYS
    assert certification_phase(started) == "RUNNING"


def test_pristine_session_conflict() -> None:
    """Predicado puro: sesión prístina ⇔ 0 eventos y 0 velas; si no, razón del rechazo."""
    assert pristine_session_conflict(0, 0) is None
    assert pristine_session_conflict(1, 0) is not None
    assert pristine_session_conflict(0, 1) is not None
    assert "paper_trade_events" in str(pristine_session_conflict(3, 0))
    assert "market_candles" in str(pristine_session_conflict(0, 2))
