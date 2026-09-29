"""Tests del runner de ventana común M9-B2B.

Cubre: ventana, paridad de señales, streaming single-pass del modelo NEW,
ledger económico OLD/NEW, summary comparable con identidades, max drawdown
REALIZED_CLOSED_TRADES y escritura atómica idempotente de artefactos.
"""

from __future__ import annotations

import json
from datetime import date

import m9b_common_window as cw
import pytest

DUR = 900_000
_GOLD = "gold-replay-" + "a" * 64
_DATASET_SHA = "b" * 64


def _stub_strategy() -> object:
    from domain.trading.signal import Action, Signal

    class Stub:
        version = "stub-v1"

        def on_candle(self, candle: object) -> Signal:
            close = candle.close  # type: ignore[attr-defined]
            ts = candle.timestamp_ms  # type: ignore[attr-defined]
            if close > 102.0:
                return Signal(timestamp_ms=ts, action=Action.BUY)
            if close < 99.0:
                return Signal(timestamp_ms=ts, action=Action.SELL)
            return Signal(timestamp_ms=ts, action=Action.HOLD)

    return Stub()


def _row(index: int, close: float, *, start_ms: int = 0) -> object:
    from infrastructure.medallion.replay import CandleRow

    return CandleRow(
        open_time=start_ms + index * DUR,
        close_time=start_ms + index * DUR + DUR,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
        trade_count=1,
    )


def _rows(n: int, *, start_ms: int = 0, up_from: int | None = None) -> list:
    return [
        _row(i, 103.0 if (up_from is not None and i >= up_from) else 101.0, start_ms=start_ms)
        for i in range(n)
    ]


def _tradeable_rows() -> list:
    closes = [101.0] * 20 + [103.0] * 10 + [98.0] * 10
    return [_row(i, close) for i, close in enumerate(closes)]


def _domain(rows: list) -> tuple:
    from infrastructure.medallion.strategy_provider import rows_to_domain_candles

    return rows_to_domain_candles(rows)


def _atr(rows: list) -> list:
    from domain.market.indicators import atr

    return atr(_domain(rows), period=14)


def _expected_hash(rows: list) -> str:
    return cw.signal_sequence_hash(cw.signal_sequence(_stub_strategy(), _domain(rows)))  # type: ignore[arg-type]


def _trades(rows: list) -> list:
    from infrastructure.medallion.replay import ReplayTrade

    return [ReplayTrade(ts=r.close_time, price=r.close, quantity=1.0) for r in rows]


def _run_old(rows: list):
    return cw.run_old_close_only(
        strategy=_stub_strategy(),
        rows=rows,
        atr_values=_atr(rows),
        expected_signal_hash=_expected_hash(rows),
    )


def _run_new(rows: list, trades=None):
    return cw.run_new_trade_sequence(
        strategy=_stub_strategy(),
        rows=rows,
        trades=_trades(rows) if trades is None else trades,
        expected_signal_hash=_expected_hash(rows),
        dataset_id=_GOLD,
        dataset_sha=_DATASET_SHA,
    )


def _identities(report, *, model: str) -> dict:
    return cw.summary_identities(
        model=model,
        strategy="baseline",
        report=report,
        dataset_id=_GOLD,
        dataset_sha=_DATASET_SHA,
        start_ms=cw.day_start_ms(date(2024, 6, 1)),
        end_ms=cw.day_start_ms(date(2024, 6, 4)),
        code_git_sha="deadbeef",
    )


def _ledger_entry(
    *,
    net: float,
    holding: int,
    exit_ts: int,
    reason: str = "stop_loss",
    gross_exec: float | None = None,
    gross_ref: float | None = None,
    fees: float = 0.0,
    slippage: float = 0.0,
) -> dict:
    if gross_exec is None:
        gross_exec = net + fees
    if gross_ref is None:
        gross_ref = gross_exec
    return {
        "record_type": "trade",
        "model": "trade_sequence",
        "entry_timestamp": exit_ts - holding,
        "exit_timestamp": exit_ts,
        "entry_reference_price": 100.0,
        "entry_execution_price": 100.0,
        "exit_reference_price": 100.0,
        "exit_execution_price": 100.0,
        "quantity": 1.0,
        "exit_reason": reason,
        "exit_reason_presentation": reason,
        "gross_reference_pnl": gross_ref,
        "gross_execution_pnl": gross_exec,
        "fees": fees,
        "slippage": slippage,
        "net_pnl": net,
        "holding_ms": holding,
    }


# --------------------------------------------------------------- ventana


def test_common_window_is_647_days_and_62112_candles() -> None:
    start_ms, end_ms = cw.common_window_bounds()
    assert cw.window_days(start_ms, end_ms) == 647
    assert cw.expected_15m_candles(start_ms, end_ms) == 62112
    assert start_ms == cw.day_start_ms(date(2023, 9, 9))
    assert end_ms == cw.day_start_ms(date(2025, 6, 17))


def test_window_math_for_three_days_and_invalid_inputs() -> None:
    start_ms = cw.day_start_ms(date(2024, 6, 1))
    end_ms = cw.day_start_ms(date(2024, 6, 4))
    assert cw.window_days(start_ms, end_ms) == 3
    assert cw.expected_15m_candles(start_ms, end_ms) == 288
    with pytest.raises(ValueError):
        cw.window_days(end_ms, start_ms)
    with pytest.raises(ValueError):
        cw.window_days(start_ms, end_ms + 1)


def test_slice_window_requires_exact_contiguous_count() -> None:
    start_ms = cw.day_start_ms(date(2024, 6, 1))
    end_ms = cw.day_start_ms(date(2024, 6, 2))
    rows = _rows(96, start_ms=start_ms)
    assert len(cw.slice_window(rows, start_ms, end_ms)) == 96
    with pytest.raises(ValueError):
        cw.slice_window(rows[:95], start_ms, end_ms)
    gapped = list(rows)
    gapped[10] = _rows(1, start_ms=start_ms + 20 * DUR)[0]
    with pytest.raises(ValueError):
        cw.slice_window(gapped, start_ms, end_ms)
    with pytest.raises(ValueError):
        cw.slice_window(rows, end_ms, end_ms + 96 * DUR)


# --------------------------------------------------------------- exit reasons


def test_exit_reason_presentation_mapping_keeps_raw() -> None:
    assert cw.normalize_exit_reason("llm_sell") == "strategy_exit"
    assert cw.normalize_exit_reason("stop_loss") == "stop_loss"
    assert cw.EXIT_REASON_PRESENTATION == {"llm_sell": "strategy_exit"}


# --------------------------------------------------------------- paridad


def test_old_and_new_use_same_candles_and_match_signal_hash() -> None:
    rows = _rows(40, up_from=20)
    old = _run_old(rows)
    new = _run_new(rows)

    assert old.report.candle_hash == new.report.candle_hash == cw.candle_sequence_hash(rows)
    assert old.report.signal_hash == new.report.signal_hash == _expected_hash(rows)
    assert old.report.parity == "PASS" and new.report.parity == "PASS"
    assert old.report.candles == new.report.candles == 40
    assert new.stats["decisions_total"] >= 1


def test_parity_fails_closed_when_hash_differs() -> None:
    rows = _rows(20, up_from=15)
    old = cw.run_old_close_only(
        strategy=_stub_strategy(),
        rows=rows,
        atr_values=_atr(rows),
        expected_signal_hash="0" * 64,
    )
    assert old.report.parity == "FAIL"


def test_signal_sequence_is_causal() -> None:
    rows = _rows(30, up_from=20)
    strategy = _stub_strategy()
    full = cw.signal_sequence(strategy, _domain(rows))  # type: ignore[arg-type]
    corrupted = list(rows)
    corrupted[29] = _rows(1, up_from=0)[0]
    after = cw.signal_sequence(strategy, _domain(corrupted))  # type: ignore[arg-type]
    assert after[:29] == full[:29]
    assert cw.candle_sequence_hash(corrupted) != cw.candle_sequence_hash(rows)


# --------------------------------------------------------------- determinismo


def test_old_model_is_deterministic() -> None:
    rows = _rows(40, up_from=20)
    first = _run_old(rows)
    second = _run_old(rows)
    assert first.report.as_payload() == second.report.as_payload()
    assert first.ledger == second.ledger
    assert cw.sha256_hex(first.report.as_payload()) == cw.sha256_hex(second.report.as_payload())


def test_new_model_is_deterministic() -> None:
    rows = _tradeable_rows()
    first = _run_new(rows)
    second = _run_new(rows)
    assert first.report.as_payload() == second.report.as_payload()
    assert first.ledger == second.ledger


# --------------------------------------------------------------- streaming


def test_new_accepts_single_pass_iterator_without_materializing(monkeypatch) -> None:
    """NEW debe pasar el iterable/iterator directo al motor (sin `list()`)."""
    rows = _tradeable_rows()
    captured: dict[str, object] = {}
    real = cw.replay_engine

    def spy(candles_15m, ctx_1h, ctx_4h, trades, scenario, provider, **kwargs):
        captured["is_iterator"] = iter(trades) is trades
        captured["is_list"] = isinstance(trades, list)
        return real(candles_15m, ctx_1h, ctx_4h, trades, scenario, provider, **kwargs)

    monkeypatch.setattr(cw, "replay_engine", spy)
    trades_iter = iter(_trades(rows))
    run = cw.run_new_trade_sequence(
        strategy=_stub_strategy(),
        rows=rows,
        trades=trades_iter,
        expected_signal_hash=_expected_hash(rows),
        dataset_id=_GOLD,
        dataset_sha=_DATASET_SHA,
    )
    assert captured["is_iterator"] is True
    assert captured["is_list"] is False
    assert len(run.ledger) >= 1


def test_new_accepts_generator_expression() -> None:
    rows = _tradeable_rows()

    def gen():
        yield from _trades(rows)

    run = cw.run_new_trade_sequence(
        strategy=_stub_strategy(),
        rows=rows,
        trades=gen(),
        expected_signal_hash=_expected_hash(rows),
        dataset_id=_GOLD,
        dataset_sha=_DATASET_SHA,
    )
    assert run.report.parity == "PASS"


# --------------------------------------------------------------- ledger


def test_old_ledger_has_required_economic_fields() -> None:
    rows = _tradeable_rows()
    run = _run_old(rows)
    assert len(run.ledger) >= 1
    row = run.ledger[0]
    for key in cw.LEDGER_REQUIRED_FIELDS:
        assert key in row, key
    assert row["model"] == "old_close_only"
    assert row["exit_reason_presentation"] == cw.normalize_exit_reason(row["exit_reason"])
    assert row["holding_ms"] >= 0
    assert row["net_pnl"] == pytest.approx(row["gross_execution_pnl"] - row["fees"])


def test_new_ledger_has_required_and_extended_fields() -> None:
    rows = _tradeable_rows()
    run = _run_new(rows)
    assert len(run.ledger) >= 1
    row = run.ledger[0]
    for key in cw.LEDGER_REQUIRED_FIELDS:
        assert key in row, key
    for key in cw.LEDGER_EXTENDED_FIELDS:
        assert key in row, key
    assert row["model"] == "trade_sequence"
    assert row["execution_model"] == "TRADE_SEQUENCE_TAKER_PROXY"
    assert row["net_pnl"] == pytest.approx(row["gross_execution_pnl"] - row["fees"])


def test_ledger_rows_are_chronological_by_exit() -> None:
    rows = _tradeable_rows()
    for run in (_run_old(rows), _run_new(rows)):
        exits = [row["exit_timestamp"] for row in run.ledger]
        assert exits == sorted(exits)


# --------------------------------------------------------------- summary


def test_summarize_ledger_metrics_are_consistent() -> None:
    ledger = (
        _ledger_entry(net=10.0, holding=1000, exit_ts=1),
        _ledger_entry(net=-5.0, holding=2000, exit_ts=2),
        _ledger_entry(net=2.5, holding=3000, exit_ts=3),
    )
    metrics = cw.summarize_ledger(ledger, capital=100.0)
    assert metrics["closed_trades"] == 3
    assert metrics["net_pnl"] == pytest.approx(7.5)
    assert metrics["expectancy"] == pytest.approx(2.5)
    assert metrics["profit_factor"] == pytest.approx(12.5 / 5.0)
    assert metrics["win_rate"] == pytest.approx(2 / 3)
    assert metrics["average_holding_ms"] == pytest.approx(2000.0)
    assert metrics["final_equity"] == pytest.approx(107.5)
    assert metrics["max_drawdown_abs"] == pytest.approx(5.0)
    assert metrics["max_drawdown_pct"] == pytest.approx(5.0 / 110.0)
    assert metrics["max_drawdown_basis"] == "REALIZED_CLOSED_TRADES"


def test_summarize_ledger_handles_empty_and_no_loss() -> None:
    empty = cw.summarize_ledger((), capital=100.0)
    assert empty["closed_trades"] == 0
    assert empty["net_pnl"] == 0.0
    assert empty["profit_factor"] is None
    assert empty["win_rate"] == 0.0
    assert empty["max_drawdown_abs"] == 0.0
    only_wins = cw.summarize_ledger((_ledger_entry(net=4.0, holding=10, exit_ts=1),), capital=100.0)
    assert only_wins["profit_factor"] is None
    assert only_wins["win_rate"] == 1.0
    assert only_wins["max_drawdown_abs"] == 0.0


def test_summary_includes_identities_and_hashes() -> None:
    rows = _tradeable_rows()
    run = _run_new(rows)
    ledger_bytes = cw.ledger_jsonl_bytes(run.ledger)
    summary = cw.build_summary(
        model="trade_sequence",
        strategy="baseline",
        ledger=run.ledger,
        ledger_bytes=ledger_bytes,
        identities=_identities(run.report, model="trade_sequence"),
        capital=1000.0,
    )
    for key in cw.SUMMARY_IDENTITY_FIELDS:
        assert key in summary, key
    assert summary["trade_ledger_sha256"] == cw.sha256_bytes(ledger_bytes)
    without = {k: v for k, v in summary.items() if k != "summary_sha256"}
    assert summary["summary_sha256"] == cw.sha256_hex(without)
    assert summary["model"] == "trade_sequence"
    assert summary["strategy"] == "baseline"
    assert summary["max_drawdown_basis"] == "REALIZED_CLOSED_TRADES"


def test_summary_is_deterministic() -> None:
    rows = _tradeable_rows()
    run = _run_new(rows)
    ledger_bytes = cw.ledger_jsonl_bytes(run.ledger)
    identities = _identities(run.report, model="trade_sequence")
    first = cw.build_summary(
        model="trade_sequence",
        strategy="baseline",
        ledger=run.ledger,
        ledger_bytes=ledger_bytes,
        identities=identities,
        capital=1000.0,
    )
    second = cw.build_summary(
        model="trade_sequence",
        strategy="baseline",
        ledger=run.ledger,
        ledger_bytes=ledger_bytes,
        identities=identities,
        capital=1000.0,
    )
    assert first == second


def test_summary_identities_reflect_old_and_new_execution_models() -> None:
    rows = _tradeable_rows()
    old = _run_old(rows)
    new = _run_new(rows)
    old_ids = _identities(old.report, model="old_close_only")
    new_ids = _identities(new.report, model="trade_sequence")
    assert old_ids["execution_model"] == "PAPER_ENGINE_CLOSE_ONLY"
    assert new_ids["execution_model"] == "TRADE_SEQUENCE_TAKER_PROXY"
    assert old_ids["candle_hash"] == new_ids["candle_hash"]
    assert old_ids["signal_hash"] == new_ids["signal_hash"]
    assert old_ids["fee_bps"] == new_ids["fee_bps"] == cw.FEE_TAKER_BPS
    assert old_ids["slippage_bps"] == new_ids["slippage_bps"] == cw.SLIPPAGE_BPS


# --------------------------------------------------------------- artefactos


def test_artifact_paths_are_deterministic() -> None:
    from pathlib import Path

    paths = cw.artifact_paths(Path("/out"), strategy="baseline", model="trade_sequence")
    assert paths.summary.name == "baseline-trade_sequence-summary.json"
    assert paths.trades.name == "baseline-trade_sequence-trades.jsonl"


def test_write_artifact_created_then_skipped(tmp_path) -> None:
    path = tmp_path / "x.json"
    payload = b'{"a":1}\n'
    assert cw.write_artifact(path, payload) == "created"
    assert path.read_bytes() == payload
    assert not path.with_name(path.name + ".part").exists()
    assert cw.write_artifact(path, payload) == "skipped"


def test_write_artifact_conflict_fails_closed(tmp_path) -> None:
    path = tmp_path / "x.json"
    cw.write_artifact(path, b'{"a":1}\n')
    with pytest.raises(cw.ArtifactConflictError):
        cw.write_artifact(path, b'{"a":2}\n')
    assert path.read_bytes() == b'{"a":1}\n'


def test_write_run_artifacts_creates_summary_and_ledger(tmp_path) -> None:
    rows = _tradeable_rows()
    for label, run in (("old", _run_old(rows)), ("new", _run_new(rows))):
        result = cw.write_run_artifacts(
            output_dir=tmp_path,
            strategy="baseline",
            model=run.report.model,
            run=run,
            identities=_identities(run.report, model=run.report.model),
            capital=1000.0,
        )
        assert result["summary_status"] == "created"
        assert result["trades_status"] == "created"
        summary_path = tmp_path / f"baseline-{run.report.model}-summary.json"
        trades_path = tmp_path / f"baseline-{run.report.model}-trades.jsonl"
        assert summary_path.is_file() and trades_path.is_file()
        summary = json.loads(summary_path.read_text())
        assert summary["trade_ledger_sha256"] == cw.sha256_bytes(trades_path.read_bytes())
        assert summary["summary_sha256"] == cw.sha256_hex(
            {k: v for k, v in summary.items() if k != "summary_sha256"}
        )
        # rerun idéntico ⇒ SKIP y bytes sin cambios
        before = trades_path.read_bytes()
        again = cw.write_run_artifacts(
            output_dir=tmp_path,
            strategy="baseline",
            model=run.report.model,
            run=run,
            identities=_identities(run.report, model=run.report.model),
            capital=1000.0,
        )
        assert again["summary_status"] == "skipped"
        assert again["trades_status"] == "skipped"
        assert trades_path.read_bytes() == before
        assert label in ("old", "new")


def test_write_run_artifacts_conflict_fails_closed(tmp_path) -> None:
    rows = _tradeable_rows()
    run = _run_new(rows)
    cw.write_run_artifacts(
        output_dir=tmp_path,
        strategy="baseline",
        model=run.report.model,
        run=run,
        identities=_identities(run.report, model=run.report.model),
        capital=1000.0,
    )
    tampered = tuple(dict(row, net_pnl=row["net_pnl"] + 1.0) for row in run.ledger)
    from dataclasses import replace

    tampered_run = replace(run, ledger=tampered)
    with pytest.raises(cw.ArtifactConflictError):
        cw.write_run_artifacts(
            output_dir=tmp_path,
            strategy="baseline",
            model=run.report.model,
            run=tampered_run,
            identities=_identities(run.report, model=run.report.model),
            capital=1000.0,
        )


# --------------------------------------------------------------- params 22B


def test_parity_scenario_uses_phase_22b_parameters() -> None:
    scenario = cw.parity_scenario("baseline-v1")
    assert scenario.scenario_id == "m9b-common-window-v1"
    assert scenario.risk.version == "risk-v2-atr-exit"
    assert scenario.risk.stop_atr_multiplier == 2.0
    assert scenario.risk.take_profit_r_multiple == 2.0
    assert scenario.risk.trailing_atr_multiplier == 3.0
    assert scenario.fee_rate == 0.001 and cw.FEE_TAKER_BPS == 10.0
    assert scenario.slippage_bps == 2.0 and cw.SLIPPAGE_BPS == 2.0
    assert scenario.intensity == "medium"
    assert scenario.sizing_mode == "risk_engine"
