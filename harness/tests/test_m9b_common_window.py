"""Tests del runner de ventana común M9-B2A (OLD close-only vs NEW trade-sequence)."""

from __future__ import annotations

from datetime import date

import m9b_common_window as cw
import pytest

DUR = 900_000


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


def _rows(n: int, *, start_ms: int = 0, up_from: int | None = None) -> list:
    from infrastructure.medallion.replay import CandleRow

    out = []
    for i in range(n):
        close = 103.0 if (up_from is not None and i >= up_from) else 101.0
        out.append(
            CandleRow(
                open_time=start_ms + i * DUR,
                close_time=start_ms + i * DUR + DUR,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1.0,
                trade_count=1,
            )
        )
    return out


def _domain(rows: list) -> tuple:
    from infrastructure.medallion.strategy_provider import rows_to_domain_candles

    return rows_to_domain_candles(rows)


def _atr(rows: list) -> list:
    from domain.market.indicators import atr

    return atr(_domain(rows), period=14)


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
        cw.slice_window(rows[:95], start_ms, end_ms)  # faltan velas
    gapped = list(rows)
    gapped[10] = _rows(1, start_ms=start_ms + 20 * DUR)[0]
    with pytest.raises(ValueError):
        cw.slice_window(gapped, start_ms, end_ms)  # no contiguas
    with pytest.raises(ValueError):
        cw.slice_window(rows, end_ms, end_ms + 96 * DUR)  # ventana vacía


# --------------------------------------------------------------- exit reasons


def test_exit_reason_presentation_mapping_keeps_raw() -> None:
    assert cw.normalize_exit_reason("llm_sell") == "strategy_exit"
    assert cw.normalize_exit_reason("stop_loss") == "stop_loss"
    assert cw.EXIT_REASON_PRESENTATION == {"llm_sell": "strategy_exit"}


# --------------------------------------------------------------- paridad


def test_old_and_new_use_same_candles_and_match_signal_hash() -> None:
    rows = _rows(40, up_from=20)
    strategy = _stub_strategy()
    candles = _domain(rows)
    expected = cw.signal_sequence_hash(cw.signal_sequence(strategy, candles))  # type: ignore[arg-type]

    old = cw.run_old_close_only(
        strategy=strategy, rows=rows, atr_values=_atr(rows), expected_signal_hash=expected
    )
    from infrastructure.medallion.replay import ReplayTrade

    trades = [ReplayTrade(ts=r.close_time, price=r.close, quantity=1.0) for r in rows[20:30]]
    new, result = cw.run_new_trade_sequence(
        strategy=strategy,
        rows=rows,
        trades=trades,
        expected_signal_hash=expected,
        dataset_id="gold-replay-" + "a" * 64,
        dataset_sha="b" * 64,
    )

    assert old.candle_hash == new.candle_hash == cw.candle_sequence_hash(rows)
    assert old.signal_hash == new.signal_hash == expected
    assert old.parity == "PASS" and new.parity == "PASS"
    assert old.candles == new.candles == 40
    assert result.stats["decisions_total"] >= 1


def test_parity_fails_closed_when_hash_differs() -> None:
    rows = _rows(20, up_from=15)
    old = cw.run_old_close_only(
        strategy=_stub_strategy(),
        rows=rows,
        atr_values=_atr(rows),
        expected_signal_hash="0" * 64,
    )
    assert old.parity == "FAIL"


def test_signal_sequence_is_causal() -> None:
    rows = _rows(30, up_from=20)
    strategy = _stub_strategy()
    full = cw.signal_sequence(strategy, _domain(rows))  # type: ignore[arg-type]
    corrupted = list(rows)
    corrupted[29] = _rows(1, up_from=0)[0]  # vela futura distinta
    after = cw.signal_sequence(strategy, _domain(corrupted))  # type: ignore[arg-type]
    assert after[:29] == full[:29]
    assert cw.candle_sequence_hash(corrupted) != cw.candle_sequence_hash(rows)


# --------------------------------------------------------------- determinismo


def test_old_model_is_deterministic() -> None:
    rows = _rows(40, up_from=20)
    candles = _domain(rows)
    expected = cw.signal_sequence_hash(cw.signal_sequence(_stub_strategy(), candles))  # type: ignore[arg-type]
    first = cw.run_old_close_only(
        strategy=_stub_strategy(),
        rows=rows,
        atr_values=_atr(rows),
        expected_signal_hash=expected,
    )
    second = cw.run_old_close_only(
        strategy=_stub_strategy(),
        rows=rows,
        atr_values=_atr(rows),
        expected_signal_hash=expected,
    )
    assert first.as_payload() == second.as_payload()
    assert cw.sha256_hex(first.as_payload()) == cw.sha256_hex(second.as_payload())


def test_new_model_is_deterministic() -> None:
    from infrastructure.medallion.replay import ReplayTrade

    rows = _rows(40, up_from=20)
    candles = _domain(rows)
    expected = cw.signal_sequence_hash(cw.signal_sequence(_stub_strategy(), candles))  # type: ignore[arg-type]
    trades = [ReplayTrade(ts=r.close_time, price=r.close, quantity=1.0) for r in rows[20:30]]
    first, res1 = cw.run_new_trade_sequence(
        strategy=_stub_strategy(),
        rows=rows,
        trades=trades,
        expected_signal_hash=expected,
        dataset_id="gold-replay-" + "a" * 64,
        dataset_sha="b" * 64,
    )
    second, res2 = cw.run_new_trade_sequence(
        strategy=_stub_strategy(),
        rows=rows,
        trades=trades,
        expected_signal_hash=expected,
        dataset_id="gold-replay-" + "a" * 64,
        dataset_sha="b" * 64,
    )
    assert first.as_payload() == second.as_payload()
    assert [r["net_pnl"] for r in res1.records] == [r["net_pnl"] for r in res2.records]


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
