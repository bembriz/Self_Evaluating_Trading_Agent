"""Unit tests for certification_snapshot pure helpers (schema v2 producer)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services import certification_snapshot as cs
from application.services.paper_runner import PaperRunSummary
from domain.market.candle import Candle
from domain.risk.config import RiskConfig


def _summary(**overrides: Any) -> PaperRunSummary:
    base: dict[str, Any] = {
        "session_id": "sess-1",
        "decision_source": "baseline",
        "strategy_version": "baseline-v1",
        "strategy_hash": "h" * 32,
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "first_timestamp_ms": 1_700_000_000_000,
        "latest_timestamp_ms": 1_700_000_900_000,
        "decisions": {"BUY": 0, "SELL": 0, "HOLD": 0},
        "fills": 0,
        "fees": 0.0,
        "slippage": 0.0,
        "latest_equity": 1000.0,
        "kill_switch_active": False,
    }
    base.update(overrides)
    return PaperRunSummary(**base)


def _event(**overrides: Any) -> PaperTradeEvent:
    base: dict[str, Any] = {
        "session_id": "sess-1",
        "strategy_version": "baseline-v1",
        "strategy_hash": "h" * 32,
        "decision_source": "baseline",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "timestamp_ms": 1_700_000_000_000,
        "action": "HOLD",
        "filled": False,
        "risk_reason": "",
        "exit_reason": "",
        "exec_price": None,
        "quantity": None,
        "fee": 0.0,
        "slippage_cost": 0.0,
        "equity": 1000.0,
        "kill_switch_active": False,
    }
    base.update(overrides)
    return PaperTradeEvent(**base)


def _candle(ts: int) -> Candle:
    return Candle(timestamp_ms=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0, turnover=1.0)


def _artifact(**overrides: Any) -> cs.RuntimeArtifact:
    base: dict[str, Any] = {
        "git_commit": "abc",
        "application_version": "0.1.0",
        "docker_image_digest": "sha256:" + "0" * 64,
        "strategy_version": "baseline-v1",
        "strategy_hash": "h" * 32,
        "risk_config_version": "risk-v1",
        "fees_slippage_config_version": cs.FEES_SLIPPAGE_CONFIG_VERSION,
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "initial_capital": 1000.0,
        "session_id": "sess-1",
        "certification_started_at_ms": 1_700_000_000_000,
    }
    base.update(overrides)
    return cs.RuntimeArtifact(**base)


def _frozen_ok(kind: str, artifact: cs.RuntimeArtifact) -> dict[str, Any]:
    frozen = {
        "git_commit": artifact.git_commit,
        "application_version": artifact.application_version,
        "docker_image_digest": artifact.docker_image_digest,
        "strategy_version": artifact.strategy_version,
        "risk_config_version": artifact.risk_config_version,
    }
    steps = list(cs._SAFEGUARD_DRILL_STEPS[kind])
    return {"type": kind, "status": "PASS", "artifact": frozen, "steps": steps}


def test_iso_utc_ms_formats_z_suffix() -> None:
    assert cs._iso_utc_ms(1_700_000_000_000).endswith("Z")
    assert cs._iso_utc_ms(0) == "1970-01-01T00:00:00Z"


def test_session_started_at_ms_uses_first_or_now() -> None:
    assert cs.session_started_at_ms(_summary(first_timestamp_ms=42), now_ms=99) == 42
    assert cs.session_started_at_ms(_summary(first_timestamp_ms=None), now_ms=99) == 99


def test_identity_helpers() -> None:
    assert cs._identity_blank(None) is True
    assert cs._identity_blank("   ") is True
    assert cs._identity_blank("x") is False
    assert cs._resolve_identity_field("  persisted ", "cfg") == "persisted"
    assert cs._resolve_identity_field("", "cfg") == "cfg"


def test_assert_no_session_conflict_ok_and_conflicts() -> None:
    cs._assert_no_session_conflict(
        persisted_symbol="ETHUSDT",
        persisted_timeframe="15m",
        configured_symbol="ETHUSDT",
        configured_timeframe="15m",
    )
    with pytest.raises(ValueError, match="conflicts with configured symbol"):
        cs._assert_no_session_conflict(
            persisted_symbol="BTCUSDT",
            persisted_timeframe="15m",
            configured_symbol="ETHUSDT",
            configured_timeframe="15m",
        )
    with pytest.raises(ValueError, match="conflicts with configured timeframe"):
        cs._assert_no_session_conflict(
            persisted_symbol="ETHUSDT",
            persisted_timeframe="1h",
            configured_symbol="ETHUSDT",
            configured_timeframe="15m",
        )


def test_runtime_artifact_resolves_and_defaults() -> None:
    artifact = cs.runtime_artifact(
        summary=_summary(),
        app_version="0.1.0",
        git_commit="abc",
        docker_image_digest="digest",
        risk_config=RiskConfig(),
        now_ms=1_700_000_000_000,
        default_symbol="ETHUSDT",
        default_timeframe="15m",
    )
    assert artifact.symbol == "ETHUSDT"
    assert artifact.session_id == "sess-1"
    assert artifact.risk_config_version == RiskConfig().version


def test_runtime_artifact_blank_session_falls_back_to_default() -> None:
    artifact = cs.runtime_artifact(
        summary=_summary(session_id="", symbol="", timeframe=""),
        app_version="0.1.0",
        git_commit="abc",
        docker_image_digest="digest",
        risk_config=RiskConfig(),
        now_ms=1,
        default_symbol="ETHUSDT",
        default_timeframe="15m",
        default_session_id="",
    )
    assert artifact.session_id == "paper-baseline-15m-ethusdt"
    assert artifact.symbol == "ETHUSDT"


def test_runtime_artifact_conflict_raises() -> None:
    with pytest.raises(ValueError, match="conflicts with configured symbol"):
        cs.runtime_artifact(
            summary=_summary(symbol="BTCUSDT"),
            app_version="0.1.0",
            git_commit="abc",
            docker_image_digest="digest",
            risk_config=RiskConfig(),
            now_ms=1,
            default_symbol="ETHUSDT",
            default_timeframe="15m",
        )


def test_version_blocks_have_ten_keys() -> None:
    artifact = _artifact()
    assert set(cs._frozen_block(artifact, 1_700_000_000_000)) == set(cs.FROZEN_VERSION_KEYS)
    assert cs._current_block(artifact, started_at_iso=None)["certification_started_at"] is None


def test_resolve_frozen_preserves_running_anchor() -> None:
    artifact = _artifact()
    running = {
        "status": None,
        "frozen": {
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "certification_started_at": "2026-01-01T00:00:00Z",
        },
    }
    preserved = cs._resolve_frozen(running, artifact)
    assert preserved["certification_started_at"] == "2026-01-01T00:00:00Z"
    not_started = cs._resolve_frozen({}, artifact)
    assert not_started["certification_started_at"] is None


def test_certification_phase() -> None:
    assert cs.certification_phase({"status": "INVALIDATED"}) == "INVALIDATED"
    assert (
        cs.certification_phase({"frozen": {"certification_started_at": "2026-01-01T00:00:00Z"}})
        == "RUNNING"
    )
    assert cs.certification_phase({"frozen": {"certification_started_at": "  "}}) == "NOT_STARTED"
    assert cs.certification_phase({}) == "NOT_STARTED"


def test_missing_start_identity() -> None:
    assert cs.missing_start_identity(_artifact()) == []
    missing = cs.missing_start_identity(_artifact(git_commit="", symbol="  "))
    assert "git_commit" in missing
    assert "symbol" in missing


def test_session_context_conflict() -> None:
    artifact = _artifact()
    assert cs.session_context_conflict({}, artifact) is None
    conflict = cs.session_context_conflict({"frozen": {"symbol": "BTCUSDT"}}, artifact)
    assert conflict is not None and "conflicts with artifact" in conflict
    assert (
        cs.session_context_conflict({"frozen": {"symbol": "ETHUSDT", "timeframe": "15m"}}, artifact)
        is None
    )


def test_pristine_session_conflict() -> None:
    assert cs.pristine_session_conflict(0, 0) is None
    assert "prior paper_trade_events" in (cs.pristine_session_conflict(3, 0) or "")
    assert "prior market_candles" in (cs.pristine_session_conflict(0, 5) or "")


def test_decision_context_coverage() -> None:
    assert cs.decision_context_coverage([]) == 100.0
    events = [
        _event(decision_context={"schema_version": "v1", "signal_reason": "x"}),
        _event(decision_context={"schema_version": "v1"}),
        _event(decision_context=None),
    ]
    assert cs.decision_context_coverage(events) == pytest.approx(100.0 / 3.0)


def test_fill_counts_and_slippage_fees() -> None:
    events = [
        _event(action="BUY", filled=True, fee=0.1, slippage_cost=0.01),
        _event(action="SELL", filled=True, exit_reason="stop_loss", fee=0.2, slippage_cost=0.02),
        _event(action="SELL", filled=True, exit_reason="", fee=0.3, slippage_cost=0.03),
        _event(action="HOLD", filled=False),
    ]
    assert cs.fill_counts(events) == (3, 1, 3)
    slip, fees = cs.slippage_and_fees(events)
    assert fees == pytest.approx(0.6)
    assert slip == pytest.approx(0.06)


def test_unexplained_gap_count() -> None:
    assert cs.unexplained_gap_count([], 900_000) == 0
    assert cs.unexplained_gap_count([_candle(0)], 900_000) == 0
    assert cs.unexplained_gap_count([_candle(0), _candle(900_000)], 0) == 0
    candles = [_candle(0), _candle(900_000), _candle(2_700_000)]
    assert cs.unexplained_gap_count(candles, 900_000) == 1


def test_market_evidence_complete() -> None:
    assert cs.market_evidence_complete(1, [], []) == "FAIL"
    assert cs.market_evidence_complete(0, [], []) == "PASS"
    assert cs.market_evidence_complete(0, [], [_event()]) == "FAIL"
    candles = [_candle(0), _candle(900_000)]
    inside = [_event(timestamp_ms=0), _event(timestamp_ms=900_000)]
    assert cs.market_evidence_complete(0, candles, inside) == "PASS"
    outside = [_event(timestamp_ms=1_800_000)]
    assert cs.market_evidence_complete(0, candles, outside) == "FAIL"


def test_metrics_heartbeats_helpers() -> None:
    assert cs.metrics_history_days(["2026-01-01", "2026-01-01", "2026-01-02"]) == 2
    assert cs.add_metrics_heartbeat({}, "2026-01-01", True) == ["2026-01-01"]
    assert cs.add_metrics_heartbeat({}, "2026-01-01", False) == []
    prev = {"metrics_heartbeats": ["2026-01-01", 7, ""]}
    assert cs.add_metrics_heartbeat(prev, "2026-01-01", True) == ["2026-01-01", ""]
    assert cs.add_metrics_heartbeat(prev, "2026-01-02", True) == ["2026-01-01", "", "2026-01-02"]


def test_state_continuity_and_recovery_integrity() -> None:
    assert cs.state_continuity({}, application_version="a", session_id="s") == "PASS"
    same = {"schema_version": 2, "application_version": "a", "session_id": "s"}
    assert cs.state_continuity(same, application_version="a", session_id="s") == "PASS"
    drift = {"schema_version": 2, "application_version": "b", "session_id": "s"}
    assert cs.state_continuity(drift, application_version="a", session_id="s") == "FAIL"
    assert cs.recovery_integrity([{"kind": "other"}]) == "PASS"
    assert cs.recovery_integrity([{"kind": "recovery_divergence"}]) == "FAIL"


def test_normalized_version_value() -> None:
    assert cs._normalized_version_value(True) is True
    assert cs._normalized_version_value(1) == 1.0
    assert cs._normalized_version_value(" x ") == "x"
    assert cs._normalized_version_value(None) is None


def test_safeguard_passes() -> None:
    artifact = _artifact()
    frozen = {
        "git_commit": artifact.git_commit,
        "application_version": artifact.application_version,
        "docker_image_digest": artifact.docker_image_digest,
        "strategy_version": artifact.strategy_version,
        "risk_config_version": artifact.risk_config_version,
    }
    evidence = {"kill_switch": _frozen_ok("kill_switch", artifact)}
    assert cs.safeguard_passes(evidence, "kill_switch", frozen) is True
    assert cs.safeguard_passes(evidence, "unknown_kind", frozen) is False
    assert cs.safeguard_passes({}, "kill_switch", frozen) is False
    assert cs.safeguard_passes({"kill_switch": "nope"}, "kill_switch", frozen) is False
    wrong_type = {"kill_switch": {**_frozen_ok("kill_switch", artifact), "type": "daily_loss"}}
    assert cs.safeguard_passes(wrong_type, "kill_switch", frozen) is False
    bad_status = {"kill_switch": {**_frozen_ok("kill_switch", artifact), "status": "FAIL"}}
    assert cs.safeguard_passes(bad_status, "kill_switch", frozen) is False
    bad_artifact = {"kill_switch": {**_frozen_ok("kill_switch", artifact), "artifact": {}}}
    assert cs.safeguard_passes(bad_artifact, "kill_switch", frozen) is False
    bad_steps = {"kill_switch": {**_frozen_ok("kill_switch", artifact), "steps": ["activate"]}}
    assert cs.safeguard_passes(bad_steps, "kill_switch", frozen) is False
    assert cs.safeguard_passes(evidence, "daily_loss", frozen) is False


def test_dict_and_string_list_helpers() -> None:
    assert cs._dict_entries([{"a": 1}, "x", {"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert cs._dict_entries("nope") == []
    assert cs._string_list(["a", "", 3, "b"]) == ["a", "b"]
    assert cs._string_list("nope") == []


def test_previous_critical_errors_and_market_regimes() -> None:
    v2 = {"schema_version": 2, "operational": {"critical_errors": [{"kind": "x"}]}}
    assert cs._previous_critical_errors(v2) == [{"kind": "x"}]
    legacy = {"critical_errors": [{"kind": "legacy"}]}
    assert cs._previous_critical_errors(legacy) == [{"kind": "legacy"}]
    assert cs._previous_critical_errors({}) == []
    assert cs._market_regimes({"market_regimes": [{"name": "trend"}]}) == [{"name": "trend"}]


def test_collect_reports_and_report_date() -> None:
    assert cs._report_date("paper-20260102-030405.md") == "2026-01-02"
    assert cs._report_date("not-a-report.md") is None
    assert cs._collect_reports({"periodic_reports": ["a.md"]}, "a.md") == ["a.md"]
    assert cs._collect_reports({"periodic_reports": ["a.md"]}, "b.md") == ["a.md", "b.md"]
    assert cs._collect_reports({}, None) == []


def test_certification_reports_complete() -> None:
    assert cs._certification_reports_complete([], []) == "PASS"
    assert (
        cs._certification_reports_complete(["2026-01-02"], ["paper-20260102-030405.md"]) == "PASS"
    )
    assert (
        cs._certification_reports_complete(["2026-01-03"], ["paper-20260102-030405.md"]) == "FAIL"
    )


def test_session_calendar_days() -> None:
    assert cs._session_calendar_days(_summary(first_timestamp_ms=None)) == 0
    two_days = _summary(first_timestamp_ms=0, latest_timestamp_ms=86_400_000)
    assert cs._session_calendar_days(two_days) == 2
    assert cs._session_calendar_days(_summary(first_timestamp_ms=5, latest_timestamp_ms=5)) == 1


def test_finite_decimal_str_and_sanitize() -> None:
    assert cs._finite_decimal_str(Decimal("1.5")) == "1.5"
    assert cs._finite_decimal_str(Decimal("NaN")) is None
    assert cs._finite_decimal_str(Decimal("Infinity")) is None
    payload = {"a": float("nan"), "b": [float("inf"), 1.0], "c": Decimal("Infinity"), "d": "ok"}
    sanitized = cs._sanitize_nonfinite(payload)
    assert sanitized == {"a": None, "b": [None, 1.0], "c": None, "d": "ok"}
    assert cs._sanitize_state({"x": float("nan")}) == {"x": None}


def test_serialize_v2_and_write(tmp_path: Path) -> None:
    state = cs._sanitize_state({"schema_version": 2, "value": float("nan"), "d": Decimal("1.5")})
    out = tmp_path / "nested" / "state.json"
    cs.write_certification_state_v2(state, out)
    text = out.read_text(encoding="utf-8")
    assert "NaN" not in text
    assert "1.5" in text
    assert not (tmp_path / "nested" / "state.json.tmp").exists()
    with pytest.raises(TypeError):
        cs._serialize_v2({"x": object()})


def test_start_certification_anchors_not_started() -> None:
    artifact = _artifact()
    state = cs.start_certification({}, artifact, now_ms=1_700_000_000_000)
    assert state["schema_version"] == 2
    assert state["session_id"] == "sess-1"
    assert str(state["frozen"]["certification_started_at"]).endswith("Z")
    assert (
        state["current"]["certification_started_at"] == state["frozen"]["certification_started_at"]
    )
    assert state["application_version"] == artifact.application_version
    assert state["status"] is None
    assert state["invalidated_reason"] is None
    assert state["operational"] == {}
    assert state["accounting_book"] is None


def test_start_certification_rejects_missing_identity() -> None:
    with pytest.raises(ValueError, match="missing mandatory identity"):
        cs.start_certification({}, _artifact(git_commit=""), now_ms=1)


def test_start_certification_rejects_session_conflict() -> None:
    previous = {"frozen": {"symbol": "BTCUSDT"}}
    with pytest.raises(ValueError, match="START rejected"):
        cs.start_certification(previous, _artifact(), now_ms=1)


def test_start_certification_running_is_noop() -> None:
    previous = {"frozen": {"certification_started_at": "2026-01-01T00:00:00Z"}, "marker": 1}
    assert cs.start_certification(previous, _artifact(), now_ms=2) == previous


def test_start_certification_reanchors_invalidated() -> None:
    previous = {"status": "INVALIDATED", "invalidated_reason": "x", "frozen": {}}
    state = cs.start_certification(previous, _artifact(), now_ms=1_700_000_000_000)
    assert state["status"] is None
    assert state["invalidated_reason"] is None
    assert str(state["frozen"]["certification_started_at"]).endswith("Z")


def test_start_certification_session_id_and_started_fallbacks() -> None:
    blank = _artifact(session_id="", symbol="ethusdt", timeframe="15m")
    assert cs.start_certification({}, blank, now_ms=1)["session_id"] == (
        "paper-baseline-15m-ethusdt"
    )
    prev = {"session_id": "persisted", "session_started_at": "2026-01-01T00:00:00Z"}
    state = cs.start_certification(prev, _artifact(), now_ms=1)
    assert state["session_id"] == "persisted"
    assert state["session_started_at"] == "2026-01-01T00:00:00Z"
