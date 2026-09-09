import json
from pathlib import Path

import paper_certification
from paper_certification import (
    CertificationReport,
    evaluate_certification,
    invalidate_state,
    reset_certification_state,
)

FROZEN_KEYS = (
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
)

CERT_START = "2026-09-01T00:00:00Z"
DAY_30 = "2026-10-01T00:00:00Z"  # 30 días exactos después
DAY_29 = "2026-09-30T00:00:00Z"  # 29 días después
DAY_29_BOUNDARY = "2026-09-30T23:59:59Z"  # 29d 23h 59m 59s


def _versions() -> dict[str, object]:
    return {
        "git_commit": "906556371d072da2e7aa47a0ed780c2f61badc3d",
        "application_version": "0.2.0",
        "strategy_version": "baseline-v1",
        "risk_config_version": "risk-v1",
        "docker_image_digest": "sha256:testdigest",
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "initial_capital": "1000.00",
        "fees_slippage_config_version": "fees-v1",
        "certification_started_at": CERT_START,
    }


def _operational(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "accounting_residual": 0.0,
        "recovery_integrity": "PASS",
        "unexplained_market_gaps": 0,
        "market_evidence_complete": "PASS",
        "decision_context_coverage": 100.0,
        "state_continuity": "PASS",
        "metrics_history_days": 30.0,
        "critical_errors": [],
        "certification_reports_complete": "PASS",
        "kill_switch_tested": "PASS",
        "daily_loss_tested": "PASS",
        "fill_count": 0,
        "closed_trade_count": 0,
        "trade_count": 0,
    }
    base.update(overrides)
    return base


def valid_state(
    *,
    evaluated_at: str = DAY_30,
    operational: dict[str, object] | None = None,
    current: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "session_id": "paper-0.2.0-20260901",
        "session_started_at": CERT_START,
        "frozen": _versions(),
        "current": current if current is not None else _versions(),
        "operational": operational if operational is not None else _operational(),
        "status": None,
        "invalidated_reason": None,
    }


def _result(state: dict[str, object], evaluated_at: str = DAY_30) -> CertificationReport:
    return evaluate_certification(state, evaluated_at=evaluated_at)


def _check(report: CertificationReport, name: str):
    return next(check for check in report.checks if check.name == name)


# --- Casos TDD obligatorios 16c.4 ---


def test_29_days_all_correct_fails() -> None:
    report = _result(valid_state(), evaluated_at=DAY_29)

    assert report.overall_status == "FAIL"
    assert "calendar_days" in report.failure_reasons[0]


def test_29d23h59m59s_fails() -> None:
    report = _result(valid_state(), evaluated_at=DAY_29_BOUNDARY)

    assert report.overall_status == "FAIL"
    assert report.certification_age_days < 30.0


def test_30_days_zero_fills_passes() -> None:
    report = _result(valid_state(operational=_operational(fill_count=0, closed_trade_count=0)))

    assert report.overall_status == "PASS"
    assert report.failure_reasons == ()


def test_30_days_one_fill_can_pass() -> None:
    report = _result(valid_state(operational=_operational(fill_count=1, trade_count=1)))

    assert report.overall_status == "PASS"


def test_500_fills_do_not_grant_pass_by_themselves() -> None:
    report = _result(valid_state(operational=_operational(fill_count=500, accounting_residual=1.0)))

    assert report.overall_status == "FAIL"
    assert "accounting_residual" in " ".join(report.failure_reasons)


def test_accounting_residual_nonzero_fails() -> None:
    report = _result(valid_state(operational=_operational(accounting_residual=0.01)))

    assert report.overall_status == "FAIL"
    assert _check(report, "accounting_residual").status == "FAIL"


def test_unexplained_gap_fails() -> None:
    report = _result(valid_state(operational=_operational(unexplained_market_gaps=1)))

    assert report.overall_status == "FAIL"
    assert _check(report, "unexplained_market_gaps").status == "FAIL"


def test_missing_decision_context_fails() -> None:
    report = _result(valid_state(operational=_operational(decision_context_coverage=99.0)))

    assert report.overall_status == "FAIL"
    assert _check(report, "decision_context_coverage").status == "FAIL"


def test_metrics_history_short_fails() -> None:
    report = _result(valid_state(operational=_operational(metrics_history_days=29.9)))

    assert report.overall_status == "FAIL"
    assert _check(report, "metrics_history_days").status == "FAIL"


def test_version_drift_fails() -> None:
    current = _versions() | {"strategy_version": "baseline-v2"}
    report = _result(valid_state(current=current))

    assert report.overall_status == "FAIL"
    assert _check(report, "frozen_versions").status == "FAIL"


def test_certification_started_at_drift_fails_without_resetting_clock() -> None:
    current = _versions() | {"certification_started_at": "2026-09-15T00:00:00Z"}
    report = _result(valid_state(current=current))

    assert report.overall_status == "FAIL"
    assert _check(report, "frozen_versions").status == "FAIL"
    # el reloj NO se re-ancla: la edad se sigue computando desde el frozen
    assert report.certification_age_days == 30.0


def test_recovery_integrity_failure_fails() -> None:
    report = _result(valid_state(operational=_operational(recovery_integrity=False)))

    assert report.overall_status == "FAIL"
    assert _check(report, "recovery_integrity").status == "FAIL"


def test_critical_error_unexplained_fails() -> None:
    report = _result(
        valid_state(
            operational=_operational(
                critical_errors=[{"message": "runner crash", "explained": False}]
            )
        )
    )

    assert report.overall_status == "FAIL"
    assert _check(report, "critical_errors").status == "FAIL"


def test_critical_error_explicitly_explained_passes() -> None:
    report = _result(
        valid_state(
            operational=_operational(
                critical_errors=[
                    {
                        "message": "runner crash 2026-09-14",
                        "explained": True,
                        "classification": "ws stale > timeout",
                    }
                ]
            )
        )
    )

    assert report.overall_status == "PASS"
    assert _check(report, "critical_errors").status == "PASS"


def test_legacy_certification_state_reads_compatibly() -> None:
    legacy = {
        "strategy_version": "baseline-v1",
        "strategy_hash": "abc",
        "active_strategy_hash": "abc",
        "calendar_days": 30,
        "trade_count": 0,
        "market_regimes": [],
        "periodic_reports": [],
    }

    report = evaluate_certification(legacy, evaluated_at=DAY_30)

    assert report.overall_status in ("FAIL", "INVALIDATED", "PASS")
    assert report is not None


def test_min_trades_absent_does_not_block_paper() -> None:
    operational = _operational()
    del operational["trade_count"]
    del operational["fill_count"]
    del operational["closed_trade_count"]

    report = _result(valid_state(operational=operational))

    assert report.overall_status == "PASS"


def test_no_averaging_each_mandatory_failure_reported() -> None:
    report = _result(
        valid_state(
            operational=_operational(
                accounting_residual=5.0,
                unexplained_market_gaps=2,
                metrics_history_days=10.0,
            )
        )
    )

    assert report.overall_status == "FAIL"
    assert len(report.failure_reasons) == 3


# --- Estado histórico ---


def test_invalidated_status_is_preserved() -> None:
    state = valid_state() | {"status": "INVALIDATED", "invalidated_reason": "operator reset"}

    report = _result(state)

    assert report.overall_status == "INVALIDATED"
    assert "operator reset" in " ".join(report.failure_reasons)


def test_invalidate_state_does_not_rewrite_previous_evidence() -> None:
    state = valid_state(operational=_operational(fill_count=12))

    archived = invalidate_state(state, reason="drift strategy_version", invalidated_at_ms=42)

    assert archived["status"] == "INVALIDATED"
    assert archived["invalidated_reason"] == "drift strategy_version"
    assert archived["invalidated_at_ms"] == 42
    assert archived["operational"]["fill_count"] == 12
    assert archived is not state
    assert state["status"] is None


# --- Resultado estructurado ---


def test_report_is_machine_readable() -> None:
    report = _result(valid_state())

    data = report.to_dict()
    assert data["overall_status"] == "PASS"
    assert data["evaluated_at"]
    assert data["certification_age_days"] == 30.0
    assert isinstance(data["checks"], list)
    assert data["failure_reasons"] == []
    for check in data["checks"]:
        assert set(check) == {"name", "status", "observed", "required", "evidence"}


def test_missing_certification_started_at_fails_calendar_without_crash() -> None:
    frozen = _versions()
    del frozen["certification_started_at"]
    state = valid_state()
    state["frozen"] = frozen

    report = _result(state)

    assert report.overall_status == "FAIL"
    assert _check(report, "calendar_days").status == "FAIL"


def test_missing_operational_block_fails_without_crash() -> None:
    state = valid_state()
    del state["operational"]

    report = _result(state)

    assert report.overall_status == "FAIL"


# --- reset_certification_state (legacy, sin cambios) ---


def test_reset_certification_state_empieza_limpio_con_la_misma_version() -> None:
    legacy = {
        "strategy_version": "baseline-v1",
        "strategy_hash": "abc",
        "active_strategy_hash": "abc",
        "calendar_days": 4,
        "trade_count": 0,
        "market_regimes": [{"name": "TREND_UP"}],
        "periodic_reports": ["reports/paper/x.md"],
        "status": "INVALIDATED",
    }

    reset = reset_certification_state(legacy)

    assert reset["strategy_version"] == "baseline-v1"
    assert reset["strategy_hash"] == "abc"
    assert reset["active_strategy_hash"] == "abc"
    assert reset["calendar_days"] == 0
    assert reset["trade_count"] == 0
    assert reset["market_regimes"] == []
    assert reset["periodic_reports"] == []
    assert "status" not in reset


# --- CLI ---


def test_cli_writes_markdown_report_with_status(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    report_path = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    state.write_text(json.dumps(valid_state()), encoding="utf-8")

    code = paper_certification.main(
        [
            "--state",
            str(state),
            "--report",
            str(report_path),
            "--evaluated-at",
            DAY_30,
        ]
    )

    text = report_path.read_text(encoding="utf-8")
    assert code == 0
    assert "PASS" in text
    assert "calendar_days" in text


def test_cli_writes_json_report(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    report_path = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    json_path = tmp_path / "PAPER_CERTIFICATION_REPORT.json"
    state.write_text(json.dumps(valid_state()), encoding="utf-8")

    code = paper_certification.main(
        [
            "--state",
            str(state),
            "--report",
            str(report_path),
            "--json-report",
            str(json_path),
            "--evaluated-at",
            DAY_30,
        ]
    )

    assert code == 0
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["overall_status"] == "PASS"


def test_cli_returns_2_for_corrupt_json(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    report_path = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    state.write_text("{", encoding="utf-8")

    code = paper_certification.main(["--state", str(state), "--report", str(report_path)])

    assert code == 2
    assert not report_path.exists()


def test_cli_invalidate_archives_and_resets(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    archive = tmp_path / "certification-state-INVALIDATED.json"
    report_path = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    state.write_text(
        json.dumps(
            {
                "strategy_version": "baseline-v1",
                "strategy_hash": "abc",
                "active_strategy_hash": "abc",
                "calendar_days": 4,
                "trade_count": 0,
                "market_regimes": [],
                "periodic_reports": [],
            }
        ),
        encoding="utf-8",
    )

    code = paper_certification.main(
        [
            "--state",
            str(state),
            "--report",
            str(report_path),
            "--invalidate",
            "--reason",
            "drift strategy_version",
            "--archive",
            str(archive),
        ]
    )

    assert code == 0
    archived = json.loads(archive.read_text(encoding="utf-8"))
    assert archived["status"] == "INVALIDATED"
    assert archived["calendar_days"] == 4
    active = json.loads(state.read_text(encoding="utf-8"))
    assert active["strategy_hash"] == "abc"
    assert active["calendar_days"] == 0
    assert "status" not in active


def test_cli_invalidate_requires_archive_and_reason(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    report_path = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    state.write_text(json.dumps(valid_state()), encoding="utf-8")

    code = paper_certification.main(
        ["--state", str(state), "--report", str(report_path), "--invalidate"]
    )

    assert code == 2
