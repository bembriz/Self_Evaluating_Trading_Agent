import json
from pathlib import Path

import paper_certification
from paper_certification import evaluate_state


def _regime_evidence(name: str) -> dict[str, object]:
    return {
        "name": name,
        "symbol": "ETHUSDT",
        "timeframe": "15m",
        "first_seen_at_ms": 1_000,
        "confirmed_at_ms": 3_000,
        "last_seen_at_ms": 3_000,
        "classifier_version": "regime-v1",
        "confirmation_candles": 3,
    }


def valid_state(
    report_path: str = "harness/tests/test_paper_certification.py",
) -> dict[str, object]:
    return {
        "strategy_version": "baseline-v1",
        "strategy_hash": "abc",
        "active_strategy_hash": "abc",
        "calendar_days": 30,
        "trade_count": 200,
        "market_regimes": [_regime_evidence("TREND_UP"), _regime_evidence("SIDEWAYS")],
        "periodic_reports": [report_path],
    }


def test_certification_passes_only_with_all_thresholds() -> None:
    state = valid_state()

    result = evaluate_state(state)

    assert result.status == "PASS"
    assert result.reasons == []


def test_certification_is_pending_until_30_calendar_days() -> None:
    state = valid_state() | {"calendar_days": 29}

    result = evaluate_state(state)

    assert result.status == "PENDING"
    assert result.reasons == ["calendar_days below minimum: 29 < 30"]


def test_certification_is_pending_until_200_trades() -> None:
    state = valid_state() | {"trade_count": 199}

    result = evaluate_state(state)

    assert result.status == "PENDING"
    assert result.reasons == ["trade_count below minimum: 199 < 200"]


def test_certification_is_pending_until_2_market_regimes() -> None:
    state = valid_state() | {"market_regimes": [_regime_evidence("TREND_UP")]}

    result = evaluate_state(state)

    assert result.status == "PENDING"
    assert result.reasons == ["market_regimes below minimum: 1 < 2"]


def test_certification_counts_distinct_valid_regime_evidence() -> None:
    state = valid_state() | {
        "market_regimes": [
            _regime_evidence("SIDEWAYS"),
            _regime_evidence("TREND_UP"),
            _regime_evidence("SIDEWAYS"),
        ]
    }

    result = evaluate_state(state)

    assert result.status == "PASS"


def test_certification_rejects_unstructured_or_invalid_regime_evidence() -> None:
    state = valid_state() | {"market_regimes": ["SIDEWAYS", {"name": ""}]}

    result = evaluate_state(state)

    assert result.status == "PENDING"
    assert result.reasons == ["market_regimes below minimum: 0 < 2"]


def test_certification_is_pending_until_periodic_reports_exist() -> None:
    state = valid_state() | {"periodic_reports": []}

    result = evaluate_state(state)

    assert result.status == "PENDING"
    assert result.reasons == ["periodic_reports missing"]


def test_certification_ignores_nonexistent_periodic_report_paths() -> None:
    state = valid_state(report_path="docs/phases/16/evidence/missing-report.md")

    result = evaluate_state(state)

    assert result.status == "PENDING"
    assert result.reasons == ["periodic_reports missing"]


def test_certification_is_invalidated_when_active_strategy_hash_changes() -> None:
    state = valid_state() | {"active_strategy_hash": "def"}

    result = evaluate_state(state)

    assert result.status == "INVALIDATED"
    assert result.reasons == ["strategy hash changed"]


def test_strategy_hash_change_invalidates_certification() -> None:
    result = evaluate_state(
        {
            "strategy_version": "baseline-v1",
            "strategy_hash": "old",
            "active_strategy_hash": "new",
            "calendar_days": 30,
            "trade_count": 200,
            "market_regimes": [_regime_evidence("TREND_UP"), _regime_evidence("SIDEWAYS")],
            "periodic_reports": ["x.md"],
        }
    )

    assert result.status == "INVALIDATED"
    assert "strategy hash changed" in result.reasons


def test_cli_writes_pending_report_with_progress(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    report = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    state.write_text(
        json.dumps(
            {
                "strategy_version": "baseline-v1",
                "strategy_hash": "pending-live-paper-hash",
                "active_strategy_hash": "pending-live-paper-hash",
                "calendar_days": 0,
                "trade_count": 0,
                "market_regimes": [],
                "periodic_reports": [],
            }
        ),
        encoding="utf-8",
    )

    code = paper_certification.main(["--state", str(state), "--report", str(report)])

    report_text = report.read_text(encoding="utf-8")
    assert code == 0
    assert "PENDING" in report_text
    assert "calendar_days 0/30" in report_text


def test_cli_returns_2_for_corrupt_json(tmp_path: Path) -> None:
    state = tmp_path / "certification-state.json"
    report = tmp_path / "PAPER_CERTIFICATION_REPORT.md"
    state.write_text("{", encoding="utf-8")

    code = paper_certification.main(["--state", str(state), "--report", str(report)])

    assert code == 2
    assert not report.exists()
