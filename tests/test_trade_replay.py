"""Unit tests del Trade-Level Replay (dos relojes, M7).

Cubre: motor puro (dos relojes, no-lookahead, trigger≠fill, SL/TP/trailing,
MFE/MAE, orden de eventos, determinismo), provider guionado, validación FAIL
CLOSED del dataset Gold, ledger idempotente y CLI.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import shutil
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from infrastructure.medallion import replay, replay_cli
from infrastructure.medallion.bronze import bronze_filename
from infrastructure.medallion.candles import CANDLE_HEADER, CANDLE_SCHEMA_VERSION, DURATION_MS
from infrastructure.medallion.candles import TIMEFRAMES as CANDLE_TIMEFRAMES
from infrastructure.medallion.gold import (
    DATASET_ID_PREFIX,
    MANIFEST_FILENAME,
    REPLAY_CONFIG_FILENAME,
    REPLAY_CONFIG_VERSION,
    create_dataset,
)
from infrastructure.medallion.replay import (
    EXECUTION_MODEL_VERSION,
    EXIT_REASONS,
    REQUIRED_RECORD_FIELDS,
    CandleFile,
    CandleRow,
    ContextSnapshot,
    DatasetValidationError,
    Decision,
    DecisionProvider,
    LedgerConflictError,
    ReplayError,
    ReplayResult,
    ReplayScenario,
    ReplayTrade,
    ScriptedScheduleProvider,
    TradeFile,
    ValidatedDataset,
    iter_trades,
    ledger_payload,
    load_candles,
    replay_engine,
    validate_dataset,
    write_ledger,
)
from infrastructure.medallion.silver import SILVER_HEADER, SILVER_SCHEMA_VERSION
from infrastructure.medallion.split_guard import SplitGuardError

DUR = 900_000
DAY = date(2024, 6, 1)
DAY_START_MS = int(datetime(2024, 6, 1, tzinfo=UTC).timestamp()) * 1000


# ------------------------------------------------------------------ helpers


def _canon(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_gz(path: Path, header: Sequence[str], rows: Sequence[Sequence[object]]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0) as gz,
        io.TextIOWrapper(gz, encoding="utf-8", newline="") as text,
    ):
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(list(row))
        text.flush()
    return path.read_bytes()


def make_candles(
    n: int,
    *,
    start_ms: int = 0,
    close: float = 101.0,
    high: float = 102.0,
    low: float = 100.0,
) -> list[CandleRow]:
    out: list[CandleRow] = []
    for i in range(n):
        open_ms = start_ms + i * DUR
        out.append(
            CandleRow(
                open_time=open_ms,
                close_time=open_ms + DUR,
                open=close,
                high=high,
                low=low,
                close=close,
                volume=1.0,
                trade_count=1,
            )
        )
    return out


def _hour_candle(open_ms: int, *, close: float = 101.0) -> CandleRow:
    return CandleRow(
        open_time=open_ms,
        close_time=open_ms + 3_600_000,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1.0,
        trade_count=1,
    )


class StaticProvider:
    """Provider de prueba: decisiones fijas por índice de vela."""

    def __init__(self, decisions: dict[int, str]) -> None:
        self._decisions = decisions
        self.calls: list[dict[str, Any]] = []

    def decide(
        self,
        *,
        candle_index: int,
        decision_ts: int,
        reference_price: float,
        atr_value: float | None,
        context: ContextSnapshot,
    ) -> Decision | None:
        self.calls.append(
            {
                "candle_index": candle_index,
                "decision_ts": decision_ts,
                "atr_value": atr_value,
                "context": context,
            }
        )
        action = self._decisions.get(candle_index)
        if action is None:
            return None
        return Decision(
            action=action,
            signal_ts=decision_ts,
            reference_price=reference_price,
            candle_index=candle_index,
            atr=atr_value,
        )


class ContextSensitiveProvider:
    """Decisiona en el índice 14 usando el close del 1h confirmado (si existe)."""

    def decide(
        self,
        *,
        candle_index: int,
        decision_ts: int,
        reference_price: float,
        atr_value: float | None,
        context: ContextSnapshot,
    ) -> Decision | None:
        if candle_index != 14:
            return None
        reference = context.h1.close if context.h1 is not None else reference_price
        return Decision(
            action="buy",
            signal_ts=decision_ts,
            reference_price=reference,
            candle_index=candle_index,
            atr=atr_value,
        )


def _engine(
    candles: Sequence[CandleRow],
    trades: Iterable[ReplayTrade],
    provider: DecisionProvider,
    *,
    ctx_1h: Sequence[CandleRow] = (),
    ctx_4h: Sequence[CandleRow] = (),
    dataset_id: str = DATASET_ID_PREFIX + "a" * 64,
    dataset_sha: str = "b" * 64,
    scenario: ReplayScenario | None = None,
) -> ReplayResult:
    return replay_engine(
        candles,
        ctx_1h,
        ctx_4h,
        trades,
        scenario if scenario is not None else replay.DEFAULT_SCENARIO,
        provider,
        dataset_id=dataset_id,
        dataset_sha=dataset_sha,
    )


def _payload(result: ReplayResult, *, ordering_fidelity: str = "PARTIAL") -> bytes:
    return ledger_payload(
        result,
        dataset_id=DATASET_ID_PREFIX + "a" * 64,
        dataset_sha="b" * 64,
        symbol="ETHUSDT",
        dates=(DAY,),
        ordering_fidelity=ordering_fidelity,
        scenario=replay.DEFAULT_SCENARIO,
    )


def _trades(rows: Sequence[tuple[int, float]]) -> list[ReplayTrade]:
    return [ReplayTrade(ts=ts, price=price, quantity=1.0) for ts, price in rows]


def _one_round_trip(result: ReplayResult) -> dict[str, Any]:
    assert len(result.records) == 1, f"esperaba 1 trade cerrado, hay {len(result.records)}"
    return result.records[0]


def _as_int(value: object) -> int:
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _as_float(value: object) -> float:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


# ------------------------------------------------------- motor: reglas base


def test_entry_fills_at_first_trade_at_or_after_decision_ts() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades(
        [
            (13_400_000, 99.0),  # antes de la señal: NO puede rellenar
            (13_500_100, 100.0),  # primer trade >= señal (13_500_000)
            (15_000_000, 102.0),
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["entry_signal_timestamp"] == 13_500_000
    assert rec["entry_trigger_timestamp"] == 13_500_000
    assert rec["entry_fill_timestamp"] == 13_500_100
    assert rec["entry_fill_timestamp"] > rec["entry_trigger_timestamp"]
    assert rec["entry_fill_timestamp"] > 13_400_000
    assert rec["entry_reference_price"] == 101.0  # close de la vela de decisión
    assert rec["entry_execution_price"] == pytest.approx(100.0 * 1.0005)
    assert rec["entry_trade_price"] == 100.0
    assert rec["exit_reason"] == "end_of_dataset"


def test_risk_exit_triggers_on_trade_and_fills_on_next_trade() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades(
        [
            (13_500_100, 100.0),  # entry fill
            (13_600_000, 97.0),  # sin breach; eleva trailing a 98.05
            (13_700_000, 95.0),  # breach → trigger
            (13_800_000, 94.0),  # fill en el siguiente trade
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "stop_loss"
    assert rec["exit_trigger_timestamp"] == 13_700_000
    assert rec["exit_fill_timestamp"] == 13_800_000
    assert rec["exit_trigger_timestamp"] < rec["exit_fill_timestamp"]
    assert rec["exit_trigger_trade_index"] == 2
    assert rec["exit_fill_trade_index"] == 3
    assert rec["exit_reference_price"] == pytest.approx(98.05)  # protective elevado
    assert rec["exit_execution_price"] == pytest.approx(94.0 * 0.9995)
    assert rec["exit_trade_price"] == 94.0
    assert rec["initial_stop"] == pytest.approx(96.05)
    assert rec["initial_target"] == pytest.approx(106.05)
    assert rec["atr_at_entry"] == pytest.approx(2.0)
    assert rec["trailing_updates"] == 1


def test_take_profit_wins_and_reference_is_target() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades(
        [
            (13_500_100, 100.0),
            (13_600_000, 107.0),  # >= target 106.05 → trigger
            (13_700_000, 106.0),  # fill
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "take_profit"
    assert rec["exit_trigger_timestamp"] == 13_600_000
    assert rec["exit_fill_timestamp"] == 13_700_000
    assert rec["exit_reference_price"] == pytest.approx(106.05)
    assert rec["exit_execution_price"] == pytest.approx(106.0 * 0.9995)


def test_trailing_stop_uses_elevated_trailing_and_classifies_above_entry() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades(
        [
            (13_500_100, 100.0),
            (13_600_000, 103.0),  # eleva trailing a 101
            (13_700_000, 105.0),  # eleva trailing a 103 (sin TP: 105 < 106.05)
            (13_800_000, 100.0),  # <= 103 → trigger trailing
            (13_900_000, 99.0),  # fill
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "trailing_stop"
    assert rec["exit_trigger_timestamp"] == 13_800_000
    assert rec["exit_reference_price"] == pytest.approx(103.0)
    assert rec["trailing_updates"] == 2
    assert rec["highest_price"] == pytest.approx(105.0)
    assert rec["mfe"] == pytest.approx(105.0 - 100.05)
    assert rec["mae"] == pytest.approx(100.05 - 100.0)


def test_new_high_trade_never_triggers_trailing_same_event() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades([(13_500_100, 100.0), (13_600_000, 105.0)])
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "end_of_dataset"
    assert rec["trailing_updates"] == 1
    assert rec["highest_price"] == pytest.approx(105.0)


def test_mfe_mae_and_highest_price_from_execution_path() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades(
        [
            (13_500_100, 100.0),
            (13_600_000, 97.5),  # mae = 100.05 - 97.5
            (13_700_000, 103.5),  # mfe = 103.5 - 100.05
            (13_800_000, 101.0),
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["mfe"] == pytest.approx(103.5 - 100.05)
    assert rec["mae"] == pytest.approx(100.05 - 97.5)
    assert rec["highest_price"] == pytest.approx(103.5)
    assert rec["mfe"] >= 0.0
    assert rec["mae"] >= 0.0


def test_pending_risk_exit_fills_before_sell_decision_at_same_trade() -> None:
    provider = StaticProvider({14: "buy", 16: "sell"})
    trades = _trades(
        [
            (13_500_100, 100.0),
            (14_000_000, 90.0),  # breach → trigger stop_loss
            (15_400_000, 95.0),  # (a) fill stop; (b) SELL en flat → no-op
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    assert len(result.records) == 1
    assert result.records[0]["exit_reason"] == "stop_loss"
    assert result.stats["decisions_dropped"] == 1
    assert result.stats["decisions_filled"] == 1


def test_sell_decision_fill_precedes_risk_evaluation_at_same_trade() -> None:
    provider = StaticProvider({14: "buy", 16: "sell"})
    trades = _trades(
        [
            (13_500_100, 100.0),
            (15_400_000, 90.0),  # SELL señal 15_300_000 <= 15_400_000: decide antes
        ]
    )
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "strategy_exit"
    assert rec["exit_trigger_timestamp"] == 15_300_000  # close de la vela 16
    assert rec["exit_fill_timestamp"] == 15_400_000
    assert rec["exit_reference_price"] == 101.0
    assert result.stats["closed_trades"] == 1


def test_buy_while_in_position_is_dropped() -> None:
    provider = StaticProvider({14: "buy", 16: "buy"})
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    result = _engine(make_candles(20), trades, provider)
    assert len(result.records) == 1
    assert result.stats["decisions_dropped"] == 1
    assert result.stats["decisions_filled"] == 1


def test_sell_while_flat_is_dropped() -> None:
    provider = StaticProvider({14: "sell"})
    result = _engine(make_candles(20), _trades([(13_500_100, 100.0)]), provider)
    assert result.records == []
    assert result.stats["decisions_total"] == 1
    assert result.stats["decisions_dropped"] == 1


def test_buy_decision_without_atr_is_dropped() -> None:
    class NoAtrProvider:
        def decide(
            self,
            *,
            candle_index: int,
            decision_ts: int,
            reference_price: float,
            atr_value: float | None,
            context: ContextSnapshot,
        ) -> Decision | None:
            if candle_index == 14:
                return Decision(
                    action="buy",
                    signal_ts=decision_ts,
                    reference_price=reference_price,
                    candle_index=candle_index,
                    atr=None,
                )
            return None

    result = _engine(make_candles(20), _trades([(13_500_100, 100.0)]), NoAtrProvider())
    assert result.records == []
    assert result.stats["decisions_dropped"] == 1


def test_decision_never_reaching_a_trade_counts_as_unfilled() -> None:
    provider = StaticProvider({14: "buy"})
    result = _engine(make_candles(20), _trades([(13_000_000, 100.0)]), provider)
    assert result.records == []
    assert result.stats["decisions_unfilled"] == 1
    assert result.stats["decisions_total"] == 1


def test_end_of_dataset_closes_open_position_at_last_trade() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades([(13_500_100, 100.0), (14_000_000, 101.0)])
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "end_of_dataset"
    assert rec["exit_trigger_timestamp"] == 14_000_000
    assert rec["exit_fill_timestamp"] == 14_000_000
    assert rec["exit_trade_price"] == 101.0
    assert rec["exit_execution_price"] == pytest.approx(101.0 * 0.9995)
    assert rec["exit_fill_trade_index"] == 1


def test_pending_risk_exit_on_final_trade_fills_at_trigger_trade() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades([(13_500_100, 100.0), (14_000_000, 95.0)])
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["exit_reason"] == "stop_loss"
    assert rec["exit_trigger_timestamp"] == 14_000_000
    assert rec["exit_fill_timestamp"] == 14_000_000  # sin trade posterior: fill en el gatillo
    assert rec["exit_execution_price"] == pytest.approx(95.0 * 0.9995)
    assert rec["exit_trigger_trade_index"] == rec["exit_fill_trade_index"] == 1


def test_accounting_identity_net_equals_gross_minus_slippage_minus_fees() -> None:
    provider = StaticProvider({14: "buy"})
    trades = _trades([(13_500_100, 100.0), (13_700_000, 95.0), (13_800_000, 94.0)])
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    qty = float(rec["quantity"])
    gross = float(rec["gross_pnl"])
    slippage = float(rec["slippage"])
    fees = float(rec["fees"])
    net = float(rec["net_pnl"])
    entry_exec = float(rec["entry_execution_price"])
    exit_exec = float(rec["exit_execution_price"])
    assert gross == pytest.approx((94.0 - 100.0) * qty)
    assert slippage == pytest.approx(0.0005 * (100.0 + 94.0) * qty)
    assert slippage >= 0.0
    assert fees == pytest.approx(0.001 * (entry_exec + exit_exec) * qty)
    assert net == pytest.approx(gross - slippage - fees, rel=1e-12)
    assert net == pytest.approx((exit_exec - entry_exec) * qty - fees, rel=1e-12)


def test_holding_ms_is_fill_to_fill() -> None:
    provider = StaticProvider({14: "buy", 16: "sell"})
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    assert rec["holding_ms"] == 15_400_000 - 13_500_100


def test_records_carry_required_contract_fields_and_catalog() -> None:
    provider = StaticProvider({14: "buy", 16: "sell"})
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    result = _engine(make_candles(20), trades, provider)
    rec = _one_round_trip(result)
    for field in REQUIRED_RECORD_FIELDS:
        assert field in rec, field
    assert rec["exit_reason"] in EXIT_REASONS
    assert rec["exit_reason"] != "UNKNOWN"
    assert rec["record_type"] == "trade"
    assert rec["strategy_version"] == "scripted-schedule-v1"
    assert rec["risk_version"] == "replay-risk-v1"
    assert rec["execution_model_version"] == EXECUTION_MODEL_VERSION
    assert rec["dataset_id"] == DATASET_ID_PREFIX + "a" * 64
    assert rec["dataset_sha"] == "b" * 64


def test_exit_reasons_cover_catalog_values() -> None:
    seen: set[str] = set()
    scenarios: list[tuple[dict[int, str], list[tuple[int, float]]]] = [
        ({14: "buy"}, [(13_500_100, 100.0), (13_700_000, 95.0), (13_800_000, 94.0)]),
        ({14: "buy"}, [(13_500_100, 100.0), (13_600_000, 107.0), (13_700_000, 106.0)]),
        ({14: "buy"}, [(13_500_100, 100.0), (15_400_000, 101.0)]),
        ({14: "buy", 16: "sell"}, [(13_500_100, 100.0), (15_400_000, 101.0)]),
    ]
    for decisions, rows in scenarios:
        result = _engine(make_candles(20), _trades(rows), StaticProvider(decisions))
        for rec in result.records:
            seen.add(str(rec["exit_reason"]))
    assert {"stop_loss", "take_profit", "end_of_dataset", "strategy_exit"} <= seen
    assert seen <= set(EXIT_REASONS)


# ------------------------------------------------- motor: no-lookahead


def test_future_candle_corruption_does_not_change_records() -> None:
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0), (20_000_000, 99.0)])
    decisions = {14: "buy", 16: "sell"}
    base = _engine(make_candles(20), trades, StaticProvider(decisions))
    poisoned = make_candles(20)
    for i in (18, 19):
        poisoned[i] = CandleRow(
            open_time=poisoned[i].open_time,
            close_time=poisoned[i].close_time,
            open=1e9,
            high=1.1e9,
            low=0.9e9,
            close=1e9,
            volume=1e9,
            trade_count=1,
        )
    corrupted = _engine(poisoned, trades, StaticProvider(decisions))
    assert _payload(base) == _payload(corrupted)


def test_future_context_candle_corruption_does_not_change_records() -> None:
    # 1hA cierra en 9_000_000 (antes de la decisión en 13_500_000);
    # 1hB cierra en 18_000_000 (después) → la decisión NO puede verla.
    ctx_1h = [_hour_candle(5_400_000, close=105.0), _hour_candle(14_400_000, close=111.0)]
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    base = _engine(make_candles(20), trades, ContextSensitiveProvider(), ctx_1h=ctx_1h)
    poisoned_ctx = [_hour_candle(5_400_000, close=105.0), _hour_candle(14_400_000, close=1e9)]
    corrupted = _engine(make_candles(20), trades, ContextSensitiveProvider(), ctx_1h=poisoned_ctx)
    assert _payload(base) == _payload(corrupted)
    first = base.records[0]
    assert first["entry_reference_price"] == 105.0  # usa el 1h cerrado, no el close de 15m


def test_context_snapshot_only_contains_candles_closed_by_decision_ts() -> None:
    ctx_1h = [_hour_candle(0), _hour_candle(3_600_000)]
    ctx_4h = [
        CandleRow(
            open_time=0,
            close_time=14_400_000,
            open=101.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=1.0,
            trade_count=1,
        )
    ]
    provider = StaticProvider({14: "buy", 18: "sell"})
    _engine(
        make_candles(20),
        _trades([(13_500_100, 100.0), (18_000_000, 101.0)]),
        provider,
        ctx_1h=ctx_1h,
        ctx_4h=ctx_4h,
    )
    assert provider.calls, "el provider debe recibir contexto"
    saw_h1 = False
    saw_h4 = False
    for call in provider.calls:
        context = call["context"]
        assert isinstance(context, ContextSnapshot)
        if context.h1 is not None:
            assert context.h1.close_time <= call["decision_ts"]
            saw_h1 = True
        if context.h4 is not None:
            assert context.h4.close_time <= call["decision_ts"]
            saw_h4 = True
    assert saw_h1 and saw_h4, "ambos timeframes de contexto deben observarse"


def test_future_trade_corruption_does_not_change_earlier_closed_records() -> None:
    trades = _trades(
        [
            (13_500_100, 100.0),
            (15_400_000, 101.0),  # salida del primer round trip
            (18_000_000, 100.0),
            (19_000_000, 100.0),
        ]
    )
    decisions = {14: "buy", 16: "sell", 20: "buy", 22: "sell"}
    base = _engine(make_candles(26), trades, StaticProvider(decisions))
    poisoned_rows = [
        ReplayTrade(ts=18_000_000, price=1e6, quantity=1.0),
        ReplayTrade(ts=19_000_000, price=1e6, quantity=1.0),
    ]
    corrupted = _engine(
        make_candles(26), list(trades[:2]) + poisoned_rows, StaticProvider(decisions)
    )
    boundary = 15_400_000
    base_early = [r for r in base.records if _as_int(r["exit_fill_timestamp"]) <= boundary]
    corrupted_early = [
        r for r in corrupted.records if _as_int(r["exit_fill_timestamp"]) <= boundary
    ]
    assert base_early, "el primer round trip debe existir en ambos"
    assert base_early == corrupted_early
    assert len(base.records) == 2  # el segundo round trip sí cambia con el futuro


def test_decisions_use_candle_close_not_future_candles() -> None:
    class CaptureProvider:
        def __init__(self) -> None:
            self.seen: list[tuple[int, int, float]] = []

        def decide(
            self,
            *,
            candle_index: int,
            decision_ts: int,
            reference_price: float,
            atr_value: float | None,
            context: ContextSnapshot,
        ) -> Decision | None:
            self.seen.append((candle_index, decision_ts, reference_price))
            return None

    candles = make_candles(20)
    provider = CaptureProvider()
    _engine(candles, _trades([(13_500_100, 100.0)]), provider)
    assert provider.seen
    for candle_index, decision_ts, reference_price in provider.seen:
        assert decision_ts == candles[candle_index].close_time
        assert reference_price == candles[candle_index].close


def test_engine_determinism_same_input_same_payload() -> None:
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    result_a = _engine(make_candles(20), trades, StaticProvider({14: "buy", 16: "sell"}))
    result_b = _engine(make_candles(20), trades, StaticProvider({14: "buy", 16: "sell"}))
    assert _payload(result_a) == _payload(result_b)


def test_ordering_fidelity_propagated_to_run_meta() -> None:
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    result = _engine(make_candles(20), trades, StaticProvider({14: "buy", 16: "sell"}))
    payload = json.loads(_payload(result).split(b"\n")[0])
    assert isinstance(payload, dict)
    assert payload["ordering_fidelity"] == "PARTIAL"
    assert payload["record_type"] == "run_meta"
    assert payload["execution_model"] == "TRADE_SEQUENCE_TAKER_PROXY"
    assert payload["candle_visibility"] == "confirmed_close_only"


def test_run_meta_has_no_wall_clock_and_expected_keys() -> None:
    trades = _trades([(13_500_100, 100.0), (15_400_000, 101.0)])
    result = _engine(make_candles(20), trades, StaticProvider({14: "buy", 16: "sell"}))
    lines = _payload(result).split(b"\n")
    assert len(lines) == 3  # run_meta + 1 trade + final vacío
    meta = json.loads(lines[0])
    assert isinstance(meta, dict)
    expected = {
        "record_type",
        "ledger_version",
        "dataset_id",
        "dataset_sha",
        "symbol",
        "dates",
        "ordering_fidelity",
        "execution_model",
        "execution_model_version",
        "strategy_version",
        "risk_version",
        "scenario",
        "candle_visibility",
        "fill_rule",
        "pnl_basis",
        "exit_reason_catalog",
        "decisions_total",
        "decisions_filled",
        "decisions_dropped",
        "decisions_unfilled",
        "closed_trades",
    }
    assert set(meta) == expected
    assert meta["closed_trades"] == 1
    assert meta["decisions_total"] == 2


# ------------------------------------------------------------- provider


def test_scripted_schedule_decisions_by_index() -> None:
    provider = ScriptedScheduleProvider()
    ctx = ContextSnapshot(decision_ts=0, h1=None, h4=None)

    def decide_at(index: int, atr: float | None = 2.0) -> Decision | None:
        return provider.decide(
            candle_index=index,
            decision_ts=(index + 1) * DUR,
            reference_price=101.0,
            atr_value=atr,
            context=ctx,
        )

    assert decide_at(5) is None
    assert decide_at(13) is None
    assert decide_at(14) is None
    first_buy = decide_at(17)
    assert first_buy is not None and first_buy.action == "buy"
    assert decide_at(17, atr=None) is None  # ATR insuficiente → sin decisión
    sell = decide_at(25)
    assert sell is not None and sell.action == "sell"
    assert decide_at(13) is None  # sell antes del mínimo programado
    second_buy = decide_at(29)
    assert second_buy is not None and second_buy.action == "buy"
    assert decide_at(37) is not None
    assert decide_at(41) is not None


def test_scripted_schedule_first_signals() -> None:
    provider = ScriptedScheduleProvider()
    ctx = ContextSnapshot(decision_ts=0, h1=None, h4=None)
    actions: dict[int, str] = {}
    for index in range(0, 60):
        decision = provider.decide(
            candle_index=index,
            decision_ts=(index + 1) * DUR,
            reference_price=101.0,
            atr_value=2.0,
            context=ctx,
        )
        if decision is not None:
            actions[index] = decision.action
    buys = [i for i, a in actions.items() if a == "buy"]
    sells = [i for i, a in actions.items() if a == "sell"]
    assert buys == [17, 29, 41, 53]
    assert sells == [25, 37, 49]
    pairs = zip(buys[: len(sells)], sells, strict=True)
    assert all(s - b == 8 for b, s in pairs)


# ------------------------------------------- fixture Gold real (parseable)


def make_gold_fixture(root: Path) -> tuple[Path, Path, Path]:
    """Silver real (gz parseable) + dataset Gold real vía create_dataset."""
    trades_dir = root / "silver" / "trades" / "ETHUSDT"
    candles_dir = root / "silver" / "candles" / "ETHUSDT"
    dest_dir = root / "gold" / "replay-datasets" / "ETHUSDT"

    day_iso = DAY.isoformat()
    offsets = [
        (12_600_000, "99.0", "1.0"),
        (16_300_000, "100.0", "1.0"),
        (17_000_000, "101.0", "1.0"),
        (18_000_000, "95.0", "1.0"),
        (19_000_000, "94.0", "1.0"),
        (23_500_000, "96.0", "1.0"),
        (27_100_000, "100.0", "1.0"),
        (28_000_000, "101.0", "1.0"),
        (29_000_000, "102.0", "1.0"),
    ]
    name = bronze_filename("ETHUSDT", DAY)
    trades_path = trades_dir / f"date={day_iso}" / name
    trade_rows = [
        [
            str(DAY_START_MS + off),
            "ETHUSDT",
            price,
            qty,
            "buy",
            str(1_000_000 + i),
            "",
            name,
            "0" * 64,
            str(i + 1),
        ]
        for i, (off, price, qty) in enumerate(offsets)
    ]
    trade_bytes = _write_gz(trades_path, SILVER_HEADER, trade_rows)

    trades_manifest: dict[str, object] = {"schema_version": SILVER_SCHEMA_VERSION, "files": {}}
    tfiles = trades_manifest["files"]
    assert isinstance(tfiles, dict)
    tfiles[name] = {
        "date": day_iso,
        "filename": name,
        "output_path": f"date={day_iso}/{name}",
        "output_sha256": _sha(trade_bytes),
        "row_count": len(trade_rows),
        "ordering_fidelity": "PARTIAL",
        "source_order_preserved": True,
        "schema_version": SILVER_SCHEMA_VERSION,
    }
    trades_dir.mkdir(parents=True, exist_ok=True)
    (trades_dir / "manifest.json").write_bytes(_canon(trades_manifest))

    candles_manifest: dict[str, object] = {
        "schema_version": CANDLE_SCHEMA_VERSION,
        "files": {},
    }
    cfiles = candles_manifest["files"]
    assert isinstance(cfiles, dict)
    tentry = tfiles[name]
    assert isinstance(tentry, dict)
    for tf in CANDLE_TIMEFRAMES:
        cname = f"ETHUSDT_{day_iso}_{tf}.csv.gz"
        rel = f"timeframe={tf}/date={day_iso}/{cname}"
        cpath = candles_dir / rel
        if tf == "15m":
            opens = [DAY_START_MS + i * DUR for i in range(40)]
        elif tf == "1h":
            opens = [DAY_START_MS + i * 3_600_000 for i in range(10)]
        elif tf == "4h":
            opens = [DAY_START_MS + i * 14_400_000 for i in range(3)]
        elif tf == "1d":
            opens = [DAY_START_MS]
        elif tf == "30m":
            opens = [DAY_START_MS + 4 * 1_800_000]
        elif tf == "5m":
            opens = [DAY_START_MS + 525 * 60_000]
        else:  # 1m
            opens = [DAY_START_MS + 270 * 60_000]
        candle_rows = [
            [
                str(o),
                str(o + DURATION_MS[tf]),
                "ETHUSDT",
                tf,
                "101.0",
                "102.0",
                "100.0",
                "101.0",
                "1.0",
                "1",
            ]
            for o in opens
        ]
        candle_bytes = _write_gz(cpath, CANDLE_HEADER, candle_rows)
        cfiles[cname] = {
            "date": day_iso,
            "timeframe": tf,
            "filename": cname,
            "output_path": rel,
            "output_sha256": _sha(candle_bytes),
            "candle_count": len(candle_rows),
            "schema_version": CANDLE_SCHEMA_VERSION,
            "source_trades": [{"path": tentry["output_path"], "sha256": tentry["output_sha256"]}],
        }
    candles_dir.mkdir(parents=True, exist_ok=True)
    (candles_dir / "manifest.json").write_bytes(_canon(candles_manifest))

    create_dataset(trades_dir, candles_dir, dest_dir, "ETHUSDT", [DAY])
    dataset_dirs = [p for p in dest_dir.iterdir() if p.is_dir()]
    assert len(dataset_dirs) == 1
    return trades_dir, candles_dir, dataset_dirs[0]


def _dataset_copy(dataset_dir: Path, root: Path) -> Path:
    target = root / "dataset-copy"
    shutil.copytree(dataset_dir, target)
    return target


def _mutate_json(path: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    data = json.loads(path.read_bytes())
    assert isinstance(data, dict)
    mutate(data)
    path.write_bytes(_canon(data))


def _manual_dataset(
    trade_files: Sequence[TradeFile] = (),
    candle_files: Sequence[CandleFile] = (),
) -> ValidatedDataset:
    return ValidatedDataset(
        dataset_id=DATASET_ID_PREFIX + "c" * 64,
        dataset_sha="d" * 64,
        symbol="ETHUSDT",
        dates=(DAY,),
        ordering_fidelity="PARTIAL",
        config={},
        trade_files=tuple(trade_files),
        candle_files=tuple(candle_files),
    )


# ------------------------------------------------------------ validación


def test_validate_dataset_ok(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    ds = validate_dataset(dataset_dir, trades_dir, candles_dir)
    assert ds.dataset_id == dataset_dir.name
    assert ds.dataset_id.startswith(DATASET_ID_PREFIX)
    assert ds.dataset_sha == _sha((dataset_dir / MANIFEST_FILENAME).read_bytes())
    assert ds.symbol == "ETHUSDT"
    assert ds.dates == (DAY,)
    assert ds.ordering_fidelity == "PARTIAL"
    assert ds.config["config_version"] == REPLAY_CONFIG_VERSION
    assert len(ds.trade_files) == 1
    assert len(ds.candle_files) == len(CANDLE_TIMEFRAMES)


def test_validate_requires_manifest(tmp_path: Path) -> None:
    with pytest.raises(DatasetValidationError):
        validate_dataset(tmp_path / "nope", tmp_path / "t", tmp_path / "c")


def test_validate_manifest_ilegible(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    (dataset_dir / MANIFEST_FILENAME).write_bytes(b"{no-json")
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_manifest_version_wrong(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        data["manifest_version"] = "gold-replay-dataset-v0"

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_allowed_split_wrong(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        data["allowed_split"] = "WALK_FORWARD"

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_bad_dates_format(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        data["dates"] = ["ayer"]

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_dataset_dirname_mismatch(tmp_path: Path) -> None:
    trades_dir, candles_dir, _dataset_dir = make_gold_fixture(tmp_path)
    original = trades_dir.parents[2] / "gold" / "replay-datasets" / "ETHUSDT"
    renamed = original.parent / "gold-replay-deadbeef"
    shutil.move(str(original), str(renamed))
    with pytest.raises(DatasetValidationError):
        validate_dataset(renamed, trades_dir, candles_dir)


def test_validate_split_guard_before_touching_silver(tmp_path: Path) -> None:
    _trades_dir, _candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    copy = _dataset_copy(dataset_dir, tmp_path)

    def mutate(data: dict[str, object]) -> None:
        data["dates"] = ["2025-06-17"]  # fuera de DEVELOPMENT

    _mutate_json(copy / MANIFEST_FILENAME, mutate)
    missing_trades = tmp_path / "missing" / "trades"
    missing_candles = tmp_path / "missing" / "candles"
    with pytest.raises(SplitGuardError):
        validate_dataset(copy, missing_trades, missing_candles)


def test_validate_trades_file_tampered_fail_closed(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    partition = next(p for p in trades_dir.rglob("*.csv.gz"))
    partition.write_bytes(partition.read_bytes() + b"X")
    with pytest.raises(replay.InputHashMismatchError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_candle_file_tampered_fail_closed(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    candle_file = next(p for p in candles_dir.rglob("*15m*.csv.gz"))
    candle_file.write_bytes(candle_file.read_bytes() + b"X")
    with pytest.raises(replay.InputHashMismatchError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_recomputed_dataset_id_mismatch(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        trades = data["trades"]
        assert isinstance(trades, dict)
        partitions = trades["partitions"]
        assert isinstance(partitions, list)
        first = partitions[0]
        assert isinstance(first, dict)
        first["row_count"] = 999

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_config_sha_mismatch(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    (dataset_dir / REPLAY_CONFIG_FILENAME).write_bytes(b"{}\n")
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_config_wrong_execution_model(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    config = json.loads((dataset_dir / REPLAY_CONFIG_FILENAME).read_bytes())
    assert isinstance(config, dict)
    config["execution_model"] = "SOMETHING_ELSE"
    (dataset_dir / REPLAY_CONFIG_FILENAME).write_bytes(_canon(config))

    def mutate(data: dict[str, object]) -> None:
        replay_cfg = data["replay_config"]
        assert isinstance(replay_cfg, dict)
        replay_cfg["sha256"] = _sha((dataset_dir / REPLAY_CONFIG_FILENAME).read_bytes())

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_config_wrong_version(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    config = json.loads((dataset_dir / REPLAY_CONFIG_FILENAME).read_bytes())
    assert isinstance(config, dict)
    config["config_version"] = "replay-config-v0"
    (dataset_dir / REPLAY_CONFIG_FILENAME).write_bytes(_canon(config))

    def mutate(data: dict[str, object]) -> None:
        replay_cfg = data["replay_config"]
        assert isinstance(replay_cfg, dict)
        replay_cfg["sha256"] = _sha((dataset_dir / REPLAY_CONFIG_FILENAME).read_bytes())

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_source_roots_mismatch(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    other = tmp_path / "other" / "candles"
    other.mkdir(parents=True)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, other)


def test_validate_missing_trade_partition_file(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    partition = next(p for p in trades_dir.rglob("*.csv.gz"))
    partition.unlink()
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_trades_schema_version_wrong(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        trades = data["trades"]
        assert isinstance(trades, dict)
        trades["schema_version"] = "bybit-spot-trades-silver-v0"

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_candles_schema_version_wrong(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        candles = data["candles"]
        assert isinstance(candles, dict)
        candles["schema_version"] = "bybit-spot-candles-silver-v0"

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


def test_validate_rejects_path_traversal(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        trades = data["trades"]
        assert isinstance(trades, dict)
        partitions = trades["partitions"]
        assert isinstance(partitions, list)
        first = partitions[0]
        assert isinstance(first, dict)
        first["path"] = "../../etc/passwd"

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)


# ------------------------------------------------- carga de datos


def test_load_candles_parses_decision_and_context(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    ds = validate_dataset(dataset_dir, trades_dir, candles_dir)
    loaded = load_candles(ds, ("15m", "1h", "4h"))
    assert set(loaded) == {"15m", "1h", "4h"}
    assert len(loaded["15m"]) == 40
    assert len(loaded["1h"]) == 10
    assert len(loaded["4h"]) == 3
    first = loaded["15m"][0]
    assert first.open_time == DAY_START_MS
    assert first.close_time == DAY_START_MS + DUR


def _valid_candle_rows() -> list[list[object]]:
    return [
        [
            str(DAY_START_MS),
            str(DAY_START_MS + DUR),
            "ETHUSDT",
            "15m",
            "101.0",
            "102.0",
            "100.0",
            "101.0",
            "1.0",
            "1",
        ],
        [
            str(DAY_START_MS + DUR),
            str(DAY_START_MS + 2 * DUR),
            "ETHUSDT",
            "15m",
            "101.0",
            "102.0",
            "100.0",
            "101.0",
            "1.0",
            "1",
        ],
    ]


def _candle_ds(
    tmp_path: Path, rows: Sequence[Sequence[object]], header: Sequence[str], count: int
) -> tuple[ValidatedDataset, Path]:
    path = tmp_path / "manual" / "15m.csv.gz"
    _write_gz(path, header, rows)
    ds = _manual_dataset(
        candle_files=(
            CandleFile(
                date=DAY,
                timeframe="15m",
                path=path,
                sha256=_sha(path.read_bytes()),
                candle_count=count,
            ),
        )
    )
    return ds, path


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        (lambda rows: [["oops", *rows[0][1:]], *rows[1:]], "header"),
        (lambda rows: [[*rows[0][:2], "BTCUSDT", *rows[0][3:]], *rows[1:]], "symbol"),
        (lambda rows: [[*rows[0][:3], "1h", *rows[0][4:]], *rows[1:]], "timeframe"),
        (lambda rows: [[*rows[0][:5], "99.0", *rows[0][6:]], *rows[1:]], "high_low"),
        (lambda rows: [[*rows[0][:7], "99.0", *rows[0][8:]], *rows[1:]], "ohlc"),
        (lambda rows: [[*rows[0][:8], "-1.0", *rows[0][9:]], *rows[1:]], "volume"),
        (lambda rows: [["no-int", *rows[0][1:]], *rows[1:]], "ts"),
        (
            lambda rows: [
                rows[0],
                [
                    str(DAY_START_MS),
                    str(DAY_START_MS + DUR),
                    "ETHUSDT",
                    "15m",
                    "101.0",
                    "102.0",
                    "100.0",
                    "101.0",
                    "1.0",
                    "1",
                ],
            ],
            "monotonic",
        ),
        (
            lambda rows: [
                [
                    str(DAY_START_MS - 60_000),
                    str(DAY_START_MS - 60_000 + DUR),
                    "ETHUSDT",
                    "15m",
                    "101.0",
                    "102.0",
                    "100.0",
                    "101.0",
                    "1.0",
                    "1",
                ],
                *rows[1:],
            ],
            "day-bounds",
        ),
        (lambda rows: [rows[0][:-1], rows[1][:-1]], "ncols"),
    ],
)
def test_load_candles_fail_closed(
    tmp_path: Path,
    mutation: Callable[[list[list[object]]], list[list[object]]],
    label: str,
) -> None:
    rows = mutation(_valid_candle_rows())
    ds, _path = _candle_ds(tmp_path, rows, CANDLE_HEADER, count=len(rows))
    with pytest.raises(ReplayError):
        load_candles(ds, ("15m",))
    assert label  # etiqueta documenta el escenario


def test_load_candles_row_count_mismatch(tmp_path: Path) -> None:
    ds, _path = _candle_ds(tmp_path, _valid_candle_rows(), CANDLE_HEADER, count=99)
    with pytest.raises(ReplayError):
        load_candles(ds, ("15m",))


def test_iter_trades_streams_canonically(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    ds = validate_dataset(dataset_dir, trades_dir, candles_dir)
    rows = list(iter_trades(ds))
    assert len(rows) == 9
    assert rows[0].ts == DAY_START_MS + 12_600_000
    assert rows[0].price == 99.0
    assert all(rows[i].ts <= rows[i + 1].ts for i in range(len(rows) - 1))


def _valid_trade_rows() -> list[list[object]]:
    return [
        [
            str(DAY_START_MS + 1000),
            "ETHUSDT",
            "100.0",
            "1.0",
            "buy",
            "1",
            "",
            "f.csv.gz",
            "0" * 64,
            "1",
        ],
        [
            str(DAY_START_MS + 2000),
            "ETHUSDT",
            "101.0",
            "1.0",
            "buy",
            "2",
            "",
            "f.csv.gz",
            "0" * 64,
            "2",
        ],
    ]


def _trade_ds(
    tmp_path: Path, rows: Sequence[Sequence[object]], header: Sequence[str], count: int
) -> ValidatedDataset:
    path = tmp_path / "manual-trades.csv.gz"
    _write_gz(path, header, rows)
    return _manual_dataset(
        trade_files=(
            TradeFile(date=DAY, path=path, sha256=_sha(path.read_bytes()), row_count=count),
        )
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: [["oops", *rows[0][1:]], *rows[1:]],
        lambda rows: [[*rows[0][:1], "no-int", *rows[0][2:]], *rows[1:]],
        lambda rows: [[*rows[0][:2], "0", *rows[0][3:]], *rows[1:]],
        lambda rows: [[*rows[0][:3], "-1.0", *rows[0][4:]], *rows[1:]],
        lambda rows: [
            rows[0],
            [
                str(DAY_START_MS),
                "ETHUSDT",
                "101.0",
                "1.0",
                "buy",
                "2",
                "",
                "f.csv.gz",
                "0" * 64,
                "2",
            ],
        ],
        lambda rows: [rows[0][:-1], rows[1][:-1]],
    ],
)
def test_iter_trades_fail_closed(
    tmp_path: Path,
    mutation: Callable[[list[list[object]]], list[list[object]]],
) -> None:
    rows = mutation(_valid_trade_rows())
    ds = _trade_ds(tmp_path, rows, SILVER_HEADER, count=len(rows))
    with pytest.raises(ReplayError):
        list(iter_trades(ds))


def test_iter_trades_row_count_mismatch(tmp_path: Path) -> None:
    ds = _trade_ds(tmp_path, _valid_trade_rows(), SILVER_HEADER, count=99)
    with pytest.raises(ReplayError):
        list(iter_trades(ds))


# --------------------------------------------------------------- ledger


def _run_pipeline(tmp_path: Path) -> tuple[ReplayResult, bytes, ValidatedDataset]:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    ds = validate_dataset(dataset_dir, trades_dir, candles_dir)
    candles = load_candles(ds, ("15m", "1h", "4h"))
    result = replay_engine(
        candles["15m"],
        candles["1h"],
        candles["4h"],
        iter_trades(ds),
        replay.DEFAULT_SCENARIO,
        ScriptedScheduleProvider(),
        dataset_id=ds.dataset_id,
        dataset_sha=ds.dataset_sha,
    )
    payload = ledger_payload(
        result,
        dataset_id=ds.dataset_id,
        dataset_sha=ds.dataset_sha,
        symbol=ds.symbol,
        dates=ds.dates,
        ordering_fidelity=ds.ordering_fidelity,
        scenario=replay.DEFAULT_SCENARIO,
    )
    return result, payload, ds


def test_pipeline_scripted_round_trips(tmp_path: Path) -> None:
    result, payload, _ds = _run_pipeline(tmp_path)
    assert result.stats["decisions_total"] == 4  # BUY@17, SELL@25, BUY@29, SELL@37
    assert result.stats["decisions_filled"] == 2
    assert result.stats["decisions_dropped"] == 1  # SELL@25 en flat
    assert result.stats["decisions_unfilled"] == 1  # SELL@37 sin trades posteriores
    assert result.stats["closed_trades"] == 2
    reasons = [rec["exit_reason"] for rec in result.records]
    assert reasons == ["stop_loss", "end_of_dataset"]
    lines = payload.split(b"\n")
    assert len(lines) == 4  # run_meta + 2 trades + final vacío
    first = result.records[0]
    assert first["entry_fill_timestamp"] == DAY_START_MS + 16_300_000
    assert first["exit_fill_timestamp"] == DAY_START_MS + 19_000_000
    assert first["exit_reference_price"] == pytest.approx(99.0)
    second = result.records[1]
    assert second["entry_fill_timestamp"] == DAY_START_MS + 27_100_000
    assert second["exit_reason"] == "end_of_dataset"


def test_ledger_payload_deterministic_across_runs(tmp_path: Path) -> None:
    _, payload_a, _ = _run_pipeline(tmp_path / "a")
    _, payload_b, _ = _run_pipeline(tmp_path / "b")
    assert payload_a == payload_b


def test_write_ledger_created_skipped_conflict(tmp_path: Path) -> None:
    _, payload, _ = _run_pipeline(tmp_path)
    target = tmp_path / "work" / "ledger.jsonl"
    assert write_ledger(target, payload) == "created"
    assert target.read_bytes() == payload
    assert write_ledger(target, payload) == "skipped"
    with pytest.raises(LedgerConflictError):
        write_ledger(target, payload + b"tampered\n")


def test_every_record_has_contract_fields_in_pipeline(tmp_path: Path) -> None:
    result, _payload_bytes, _ds = _run_pipeline(tmp_path)
    for rec in result.records:
        for field in REQUIRED_RECORD_FIELDS:
            assert field in rec, field
        assert rec["exit_reason"] in EXIT_REASONS
        assert _as_float(rec["net_pnl"]) == pytest.approx(
            _as_float(rec["gross_pnl"]) - _as_float(rec["slippage"]) - _as_float(rec["fees"])
        )
        assert _as_float(rec["slippage"]) >= 0.0
        assert _as_int(rec["exit_fill_timestamp"]) >= _as_int(rec["exit_trigger_timestamp"])


# ------------------------------------------------------------------ CLI


def _cli_args(trades_dir: Path, candles_dir: Path, dataset_dir: Path, ledger: Path) -> list[str]:
    return [
        "--dataset-dir",
        str(dataset_dir),
        "--trades-dir",
        str(trades_dir),
        "--candles-dir",
        str(candles_dir),
        "--ledger-path",
        str(ledger),
    ]


def test_cli_created_then_skipped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    ledger = tmp_path / "work" / "ledger.jsonl"
    args = _cli_args(trades_dir, candles_dir, dataset_dir, ledger)
    rc1 = replay_cli.main(args)
    out1 = capsys.readouterr()
    assert rc1 == 0, out1.err
    assert "STATUS=created" in out1.out
    assert "SUMMARY created=1 skipped=0" in out1.out
    assert dataset_dir.name in out1.out
    rc2 = replay_cli.main(args)
    out2 = capsys.readouterr()
    assert rc2 == 0, out2.err
    assert "STATUS=skipped" in out2.out
    assert "SUMMARY created=0 skipped=1" in out2.out


def test_cli_ledger_conflict_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    ledger = tmp_path / "work" / "ledger.jsonl"
    args = _cli_args(trades_dir, candles_dir, dataset_dir, ledger)
    assert replay_cli.main(args) == 0
    capsys.readouterr()
    ledger.write_bytes(ledger.read_bytes() + b"x")
    rc = replay_cli.main(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err


def test_cli_marker_missing_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    args = _cli_args(trades_dir, candles_dir, dataset_dir, tmp_path / "l.jsonl")
    args += ["--require-marker", str(tmp_path / "no-marker")]
    rc = replay_cli.main(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err


def test_cli_split_guard_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _trades_dir, _candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    copy = _dataset_copy(dataset_dir, tmp_path)

    def mutate(data: dict[str, object]) -> None:
        data["dates"] = ["2025-06-17"]

    _mutate_json(copy / MANIFEST_FILENAME, mutate)
    args = _cli_args(
        tmp_path / "missing" / "trades",
        tmp_path / "missing" / "candles",
        copy,
        tmp_path / "l.jsonl",
    )
    rc = replay_cli.main(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "DEVELOPMENT" in captured.err
    assert not (tmp_path / "l.jsonl").exists()


def test_cli_tampered_dataset_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)
    partition = next(p for p in trades_dir.rglob("*.csv.gz"))
    partition.write_bytes(partition.read_bytes() + b"X")
    rc = replay_cli.main(_cli_args(trades_dir, candles_dir, dataset_dir, tmp_path / "l.jsonl"))
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err
    assert not (tmp_path / "l.jsonl").exists()


def test_validate_empty_dates(tmp_path: Path) -> None:
    trades_dir, candles_dir, dataset_dir = make_gold_fixture(tmp_path)

    def mutate(data: dict[str, object]) -> None:
        data["dates"] = []

    _mutate_json(dataset_dir / MANIFEST_FILENAME, mutate)
    with pytest.raises(DatasetValidationError):
        validate_dataset(dataset_dir, trades_dir, candles_dir)
