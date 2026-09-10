from __future__ import annotations

import random
from dataclasses import replace
from decimal import Decimal

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.accounting_reconciliation import (
    AccountingLedger,
    BookState,
    MissingMarkError,
    latest_persisted_mark,
    reconcile_accounting,
    reconcile_with_book,
    residual,
)
from application.services.paper_engine import PaperEngine
from domain.market.candle import Candle
from domain.portfolio.portfolio import Portfolio
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.fees import FeeModel
from domain.trading.fill import Fill
from domain.trading.signal import Action, Intensity
from domain.trading.slippage import SlippageModel

_CAPITAL = 100_000.0
_INTERVAL_MS = 900_000
_START_MS = 1_000_000_000

# Velas/decisiones deterministas. Cierres elegidos para NO disparar stop/tp antes
# de la intención (TP x100 y trailing x100 del ATR).
_SCEN_FLAT: list[tuple[float, Action]] = [
    (65000.0, Action.BUY),
    (65200.0, Action.HOLD),
    (65500.0, Action.SELL),
    (65000.0, Action.HOLD),
]
_SCEN_OPEN: list[tuple[float, Action]] = [
    (65000.0, Action.BUY),
    (65200.0, Action.HOLD),
    (65100.0, Action.HOLD),
]
_SCEN_MULTI: list[tuple[float, Action]] = [
    (65000.0, Action.BUY),
    (65200.0, Action.HOLD),
    (65500.0, Action.SELL),
    (65000.0, Action.BUY),
    (64800.0, Action.HOLD),  # cae bajo el stop => SELL stop_loss (fill real)
    (65100.0, Action.HOLD),  # flat al cierre
]


def _config() -> RiskConfig:
    return replace(
        RiskConfig(),
        capital=_CAPITAL,
        max_position_allocation=0.03,
        take_profit_r_multiple=100.0,
        trailing_atr_multiplier=100.0,
    )


def _decision(action: Action, price: float, ts: int) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts, action=action, confidence=0.8, intensity=Intensity.MEDIUM
    )


def _candle(close: float, ts: int) -> Candle:
    return Candle(
        timestamp_ms=ts,
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=10.0,
        turnover=close * 10.0,
    )


def _scenario(
    closes_actions: list[tuple[float, Action]],
) -> tuple[list[PaperTradeEvent], list[Candle], PaperEngine]:
    """Reproduce paper_runner._process: cada vela -> engine.on_price -> equity.

    `equity` persistido = mark_to_market(close) DESPUÉS de procesar la vela
    (paper_runner.py:478), igual que hará el productor real sobre la DB.
    """
    engine = PaperEngine(config=_config())
    events: list[PaperTradeEvent] = []
    candles: list[Candle] = []
    for i, (close, action) in enumerate(closes_actions):
        ts = _START_MS + i * _INTERVAL_MS
        paper_event = engine.on_price(
            decision=_decision(action, close, ts), price=close, atr=40.0, timestamp_ms=ts
        )
        equity = engine.mark_to_market(price=close)
        fill = paper_event.fill
        events.append(
            PaperTradeEvent(
                session_id="recon",
                strategy_version="baseline-v1",
                strategy_hash="h",
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
            )
        )
        candles.append(_candle(close, ts))
    return events, candles, engine


def _book(events: list[PaperTradeEvent]) -> float:
    return events[-1].equity


def _recon(events: list[PaperTradeEvent], *, mark_price: float | None) -> AccountingLedger:
    return reconcile_accounting(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark_price,
        interval_ms=_INTERVAL_MS,
    )


# ---------------------------------------------------------------- casos 1-5


def test_case1_flat_exact_reconciliation_residual_zero() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    ledger = _recon(events, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) == Decimal("0")
    assert ledger.reconstructed_equity == Decimal(str(_book(events)))
    assert ledger.position_qty == Decimal("0")
    assert ledger.average_entry == Decimal("0")


def test_case1b_flat_accepts_missing_mark() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    # Posición plana: mark_price None no debe elevar MissingMarkError.
    ledger = _recon(events, mark_price=None)
    assert residual(_book(events), ledger) == Decimal("0")


def test_case1c_empty_session_reconciles_to_capital() -> None:
    events, candles, engine = _scenario([])
    ledger = _recon(events, mark_price=latest_persisted_mark(candles))
    assert residual(engine.portfolio.equity(0.0), ledger) == Decimal("0")
    assert ledger.reconstructed_equity == Decimal(str(_CAPITAL))


def test_case2_open_position_exact_reconciliation_residual_zero() -> None:
    events, candles, engine = _scenario(_SCEN_OPEN)
    mark = latest_persisted_mark(candles)
    assert mark is not None
    ledger = _recon(events, mark_price=mark)
    assert residual(_book(events), ledger) == Decimal("0")
    assert ledger.reconstructed_equity == Decimal(str(_book(events)))
    assert ledger.position_qty == Decimal(str(engine.portfolio.position))
    assert ledger.average_entry == Decimal(str(engine.portfolio.avg_entry or 0.0))


def test_case3_multiple_buy_sell_fills_residual_zero() -> None:
    events, candles, engine = _scenario(_SCEN_MULTI)
    ledger = _recon(events, mark_price=latest_persisted_mark(candles))
    fills = [e for e in events if e.filled]
    assert len(fills) == 4  # BUY, SELL, BUY, SELL(stop)
    assert residual(_book(events), ledger) == Decimal("0")
    assert ledger.position_qty == Decimal(str(engine.portfolio.position))
    assert ledger.realized_pnl == Decimal(str(engine.portfolio.realized_pnl))
    assert ledger.fees == Decimal(str(engine.portfolio.total_fees))


def test_case3b_order_independent_sorted_by_timestamp() -> None:
    events, candles, engine = _scenario(_SCEN_MULTI)
    shuffled = list(reversed(events))
    ledger = _recon(shuffled, mark_price=latest_persisted_mark(candles))
    assert residual(engine.portfolio.equity(65100.0), ledger) == Decimal("0")


def test_case4_fees_included_exactly_once_residual_zero() -> None:
    events, candles, engine = _scenario(_SCEN_FLAT)
    assert engine.portfolio.total_fees > 0.0
    ledger = _recon(events, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) == Decimal("0")
    assert ledger.fees == Decimal(str(engine.portfolio.total_fees))


def test_case5_slippage_embedded_in_exec_price_not_double_deducted() -> None:
    events, candles, engine = _scenario(_SCEN_FLAT)
    fills = [e for e in events if e.filled]
    for e in fills:
        assert e.exec_price is not None and e.slippage_cost > 0.0
        # exec_price ya embebe slippage (precio de vela * (1 ± rate)).
        assert e.exec_price != pytest.approx(0.0)
    mark = latest_persisted_mark(candles)
    assert mark is not None
    # Caso "idéntico" => 0 exacto: la caja del fill usa exec_price y NO resta
    # slippage_cost aparte (doble deducción rompería el cero exacto).
    ledger = _recon(events, mark_price=mark)
    assert residual(_book(events), ledger) == Decimal("0")
    # Slippage_cost corrupto NO afecta a la reconstrucción: prueba que el módulo
    # nunca lo descuenta de la caja (no es un coste de flujo de caja).
    corrupted = [replace(e, slippage_cost=12_345.0) for e in events]
    ledger_corrupt = _recon(corrupted, mark_price=mark)
    assert ledger_corrupt.reconstructed_equity == ledger.reconstructed_equity
    assert residual(_book(events), ledger_corrupt) == Decimal("0")


# ---------------------------------------------------------------- casos 6-10


def test_case6_altered_fill_price_residual_nonzero() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    altered = list(events)
    assert altered[0].exec_price is not None
    altered[0] = replace(altered[0], exec_price=altered[0].exec_price + 17.25)
    ledger = _recon(altered, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) != Decimal("0")


def test_case6b_altered_fill_quantity_residual_nonzero() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    altered = list(events)
    assert altered[0].quantity is not None
    altered[0] = replace(altered[0], quantity=altered[0].quantity * 1.5)
    ledger = _recon(altered, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) != Decimal("0")


def test_case7_altered_fee_residual_nonzero() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    altered = list(events)
    altered[0] = replace(altered[0], fee=altered[0].fee + 50.0)
    ledger = _recon(altered, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) != Decimal("0")


def test_case8_missing_persisted_fill_residual_nonzero() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    missing = events[1:]  # el BUY que abrió la posición desapareció de la evidencia
    ledger = _recon(missing, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) != Decimal("0")


def test_case9_missing_mark_with_open_position_raises() -> None:
    events, _, _ = _scenario(_SCEN_OPEN)
    with pytest.raises(MissingMarkError):
        _recon(events, mark_price=None)


def test_case10_corrupted_evidence_phantom_fill_residual_nonzero() -> None:
    events, candles, _ = _scenario(_SCEN_MULTI)
    phantom = events[0]
    assert phantom.filled and phantom.exec_price is not None and phantom.quantity is not None
    duplicated = list(events) + [
        replace(
            phantom,
            timestamp_ms=_START_MS + len(events) * _INTERVAL_MS,
        )
    ]
    ledger = _recon(duplicated, mark_price=latest_persisted_mark(candles))
    assert residual(_book(events), ledger) != Decimal("0")


def test_parity_regression_seeded_full_close_roundtrips_residual_zero() -> None:
    """Regresión de paridad: 300 round-trips seedeados, residual exacto 0.

    Cada iteración construye un BUY+SELL de cierre completo con la aritmética
    REAL del engine (FeeModel/SlippageModel + Portfolio de src) y reconcilia los
    mismos operandos persistidos. Reproduce el grouping de portfolio.py:81
    (`cash += (notional*scale) - exit_fee`): si el mirror agrupara
    `(cash + notional*scale) - exit_fee`, ~23% de los cierres divergirían 1 ulp y
    este test fallaría con residual != 0.
    """
    rng = random.Random(20260909)
    fee_model = FeeModel()
    slip_model = SlippageModel()
    buy_ts = _START_MS
    for i in range(300):
        capital = float(rng.uniform(50_000.0, 250_000.0))
        buy_price = float(rng.uniform(1500.0, 4000.0))
        buy_exec = buy_price * (1.0 + slip_model.rate)  # engine _make_fill/_open_position
        buy_qty = (capital * float(rng.uniform(0.05, 0.6))) / buy_exec
        buy_notional = buy_qty * buy_exec
        buy_fee = fee_model.fee(buy_notional)
        buy_fill = Fill(
            timestamp_ms=buy_ts + i * 1_000,
            action=Action.BUY,
            price=buy_price,
            exec_price=buy_exec,
            quantity=buy_qty,
            notional=buy_notional,
            fee=buy_fee,
            slippage_cost=buy_qty * (buy_exec - buy_price),
        )
        sell_price = buy_price * float(rng.uniform(0.95, 1.05))
        sell_exec = sell_price * (1.0 - slip_model.rate)  # engine _make_fill (SELL)
        sell_notional = buy_qty * sell_exec
        sell_fee = fee_model.fee(sell_notional)
        sell_fill = Fill(
            timestamp_ms=buy_ts + i * 1_000 + 1,
            action=Action.SELL,
            price=sell_price,
            exec_price=sell_exec,
            quantity=buy_qty,  # cierre completo (engine _close_position)
            notional=sell_notional,
            fee=sell_fee,
            slippage_cost=buy_qty * (sell_price - sell_exec),
        )
        portfolio = Portfolio(initial_cash=capital, cash=capital)
        portfolio.apply_buy(buy_fill)
        portfolio.apply_sell(sell_fill)
        assert portfolio.position == 0.0  # cierre completo, sin resto
        events = [
            PaperTradeEvent(
                session_id="recon",
                strategy_version="v",
                strategy_hash="h",
                decision_source="baseline",
                symbol="ETHUSDT",
                timeframe="15m",
                timestamp_ms=buy_ts + i * 1_000,
                action="BUY",
                filled=True,
                risk_reason="",
                exit_reason="",
                exec_price=buy_exec,
                quantity=buy_qty,
                fee=buy_fee,
                slippage_cost=buy_fill.slippage_cost,
                equity=0.0,
                kill_switch_active=False,
            ),
            PaperTradeEvent(
                session_id="recon",
                strategy_version="v",
                strategy_hash="h",
                decision_source="baseline",
                symbol="ETHUSDT",
                timeframe="15m",
                timestamp_ms=buy_ts + i * 1_000 + 1,
                action="SELL",
                filled=True,
                risk_reason="",
                exit_reason="llm_sell",
                exec_price=sell_exec,
                quantity=buy_qty,
                fee=sell_fee,
                slippage_cost=sell_fill.slippage_cost,
                equity=portfolio.cash,
                kill_switch_active=False,
            ),
        ]
        ledger = reconcile_accounting(
            events,
            initial_capital=capital,
            mark_price=None,
            interval_ms=_INTERVAL_MS,
        )
        assert residual(portfolio.cash, ledger) == Decimal("0"), (
            f"round-trip #{i}: book={portfolio.cash!r} reconstructed="
            f"{ledger.reconstructed_equity!r}"
        )


# ---------------------------------------------------------------- helpers puros


def test_latest_persisted_mark_empty_is_none() -> None:
    assert latest_persisted_mark([]) is None


def test_latest_persisted_mark_returns_last_close() -> None:
    candles = [_candle(65000.0, _START_MS), _candle(65200.0, _START_MS + _INTERVAL_MS)]
    assert latest_persisted_mark(candles) == 65200.0


def test_residual_matches_definition() -> None:
    events, candles, _ = _scenario(_SCEN_FLAT)
    ledger = _recon(events, mark_price=latest_persisted_mark(candles))
    book = _book(events)
    assert residual(book, ledger) == Decimal(str(book)) - ledger.reconstructed_equity


# ------------------------------------------- 16c.6 three-way con checkpoint

_MARK = 110.0


def _make_event(
    *,
    ts: int,
    session: str,
    action: str,
    filled: bool,
    exec_price: float | None,
    quantity: float | None,
    fee: float,
    equity: float,
) -> PaperTradeEvent:
    return PaperTradeEvent(
        session_id=session,
        strategy_version="v",
        strategy_hash="h",
        decision_source="baseline",
        symbol="ETHUSDT",
        timeframe="15m",
        timestamp_ms=ts,
        action=action,
        filled=filled,
        risk_reason="",
        exit_reason="",
        exec_price=exec_price,
        quantity=quantity,
        fee=fee,
        slippage_cost=0.0,
        equity=equity,
        kill_switch_active=False,
    )


def _fill(ts: int, *, action: Action, exec_price: float, quantity: float, fee: float) -> Fill:
    return Fill(
        timestamp_ms=ts,
        action=action,
        price=exec_price,
        exec_price=exec_price,
        quantity=quantity,
        notional=quantity * exec_price,
        fee=fee,
        slippage_cost=0.0,
    )


def _record(
    pf: Portfolio,
    events: list[PaperTradeEvent],
    *,
    ts: int,
    action: str,
    mark: float,
    exec_price: float | None = None,
    quantity: float | None = None,
    fee: float = 0.0,
    session: str = "recon-book",
) -> None:
    """Replica paper_runner._process sobre un Portfolio real y persiste el evento.

    La equity persistida es ``pf.equity(mark)`` DESPUÉS de procesar el fill (igual
    que el engine en la frontera de vela). ``mark`` = close de la vela del evento.
    """
    filled = action in ("BUY", "SELL")
    if action == "BUY":
        assert exec_price is not None and quantity is not None
        pf.apply_buy(
            _fill(ts, action=Action.BUY, exec_price=exec_price, quantity=quantity, fee=fee)
        )
    elif action == "SELL":
        assert exec_price is not None and quantity is not None
        pf.apply_sell(
            _fill(ts, action=Action.SELL, exec_price=exec_price, quantity=quantity, fee=fee)
        )
    events.append(
        _make_event(
            ts=ts,
            session=session,
            action=action,
            filled=filled,
            exec_price=exec_price if filled else None,
            quantity=quantity if filled else None,
            fee=fee if filled else 0.0,
            equity=pf.equity(mark),
        )
    )


def _book_from_portfolio(p: Portfolio, *, mark: float, cursor_ts: int | None) -> BookState:
    """Checkpoint autoritativo: estado real del Portfolio + cursor del último evento."""
    return BookState(
        cash=Decimal(str(p.cash)),
        position_qty=Decimal(str(p.position)),
        average_entry=Decimal(str(p.avg_entry)) if p.avg_entry is not None else None,
        realized_pnl=Decimal(str(p.realized_pnl)),
        fees=Decimal(str(p.total_fees)),
        equity=Decimal(str(p.equity(mark))),
        entry_fees=Decimal(str(p.entry_fees)),
        last_event_ms=cursor_ts,
    )


def _open_capital() -> tuple[Portfolio, list[PaperTradeEvent], float]:
    """BUY 1.0@100 fee 0.1 con posición abierta (evento real del Portfolio)."""
    pf = Portfolio(initial_cash=_CAPITAL, cash=_CAPITAL)
    events: list[PaperTradeEvent] = []
    _record(pf, events, ts=0, action="BUY", mark=_MARK, exec_price=100.0, quantity=1.0, fee=0.1)
    return pf, events, _MARK


def _flat_capital() -> tuple[Portfolio, list[PaperTradeEvent], float]:
    """Round-trip completo BUY 1.0@100 / SELL 1.0@110 (flat al cierre)."""
    pf = Portfolio(initial_cash=_CAPITAL, cash=_CAPITAL)
    events: list[PaperTradeEvent] = []
    _record(pf, events, ts=0, action="BUY", mark=_MARK, exec_price=100.0, quantity=1.0, fee=0.1)
    _record(pf, events, ts=1, action="SELL", mark=_MARK, exec_price=110.0, quantity=1.0, fee=0.2)
    return pf, events, _MARK


def test_compensating_corruption_fee_up_preserves_equity_fails() -> None:
    """Fee↑ + price/qty↓ que conserva la equity final: la paridad de equity NO basta.

    Checkpoint bueno (Portfolio real, BUY 1.0@100 fee 0.1, cursor 0, equity@110 =
    100009.9). Eventos viejos alterados (BUY 0.5@80 fee 5.1 en ts 0 <= cursor)
    reconstruyen la MISMA equity (99954.9 + 0.5*110 = 100009.9) pero con
    cash/posición/fees/avg distintos ⇒ full (corrupto) != incremental (checkpoint):
    FAIL por componentes aunque equity(book)==equity(reconstruida).
    """
    pf, events, mark = _open_capital()
    book = _book_from_portfolio(pf, mark=mark, cursor_ts=0)
    corrupted = events[:1]  # mismos ts (evento viejo, ts 0 <= cursor)
    assert corrupted[0].exec_price is not None
    corrupted[0] = replace(corrupted[0], exec_price=80.0, quantity=0.5, fee=5.1, equity=100009.9)

    result = reconcile_with_book(
        corrupted,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert result.status == "FAIL"
    assert result.accounting_residual != Decimal("0")
    assert "cash" in result.mismatches
    assert "fees" in result.mismatches
    assert "equity" not in result.mismatches  # la equity SÍ coincide (corrupción compensada)


def test_same_final_equity_wrong_position_cash_decomposition_fails() -> None:
    """Misma equity final pero descomposición position/cash distinta del checkpoint.

    Checkpoint bueno = Portfolio real BUY 1.0@100 (pos 1.0, cash 99899.9, cursor 1).
    Corrupción de eventos viejos: re-partir en BUY 0.4@85 + BUY 0.3@110 (pos 0.7,
    cash 99932.9) que reconstruye la misma equity (99932.9 + 0.7*110 = 100009.9)
    pero con la posición y la caja descompuestas de otra forma ⇒ full != incremental
    ⇒ FAIL componente a componente aunque equity(checkpoint)==equity(reconstruida).
    """
    pf, events, mark = _open_capital()
    _record(pf, events, ts=1, action="HOLD", mark=mark)  # checkpoint cubre ts 0..1
    book = _book_from_portfolio(pf, mark=mark, cursor_ts=1)
    corrupted = [
        _make_event(
            ts=0,
            session="recon-book",
            action="BUY",
            filled=True,
            exec_price=85.0,
            quantity=0.4,
            fee=0.05,
            equity=100009.9,
        ),
        _make_event(
            ts=1,
            session="recon-book",
            action="BUY",
            filled=True,
            exec_price=110.0,
            quantity=0.3,
            fee=0.05,
            equity=100009.9,
        ),
    ]

    result = reconcile_with_book(
        corrupted,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert result.status == "FAIL"
    assert result.accounting_residual != Decimal("0")
    assert "cash" in result.mismatches
    assert "position_qty" in result.mismatches


def test_first_write_no_previous_book_is_baseline_pass() -> None:
    """Sin checkpoint previo (primer ancla / sesión nueva) ⇒ PASS baseline residual 0."""
    pf, events, mark = _open_capital()

    result = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert result.status == "PASS"
    assert result.accounting_residual == Decimal("0")
    assert result.mismatches == ()
    # El libro devuelto es la reconstrucción actual + cursor, usable como nuevo ancla.
    assert result.book.cash == Decimal(str(pf.cash))
    assert result.book.equity == Decimal(str(pf.equity(mark)))
    assert result.book.last_event_ms == 0


def test_f2_case1_legit_fill_between_writes_passes_and_checkpoint_advances() -> None:
    """(F2-1) Fill legítimo entre dos writes ⇒ PASS y el cursor del checkpoint avanza."""
    pf, events, mark = _open_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert first.status == "PASS"
    assert first.book.last_event_ms == 0

    _record(pf, events, ts=1, action="BUY", mark=mark, exec_price=105.0, quantity=1.0, fee=0.2)
    second = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=first.book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "PASS"
    assert second.mismatches == ()
    assert second.book.last_event_ms == 1  # el checkpoint AVANZA sobre el fill nuevo
    first_cursor = first.book.last_event_ms
    second_cursor = second.book.last_event_ms
    assert first_cursor is not None and second_cursor is not None
    assert second_cursor > first_cursor
    assert second.book.cash == Decimal(str(pf.cash))
    assert second.book.position_qty == Decimal(str(pf.position))
    assert second.book.average_entry == Decimal(str(pf.avg_entry or 0.0))


def test_f2_case2_second_write_without_new_events_still_passes() -> None:
    """(F2-2) Segundo write sin eventos nuevos ⇒ sigue PASS (no-wedge)."""
    pf, events, mark = _open_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    second = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=first.book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "PASS"
    assert second.mismatches == ()
    assert second.book.last_event_ms == first.book.last_event_ms
    assert second.book.to_dict() == first.book.to_dict()


def test_f2_case3_mark_drift_with_open_position_between_writes_passes() -> None:
    """(F2-3) Drift de mark con posición abierta ⇒ PASS: los 3 caminos usan el MISMO mark.

    El checkpoint quedó con la posición abierta marcada a 110; entre writes llegan
    velas nuevas (close 120) con un evento HOLD en la frontera ⇒ la reconstrucción
    full/incremental y la equity live del último evento usan el mismo mark 120.
    """
    pf, events, _ = _open_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=_MARK,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert first.status == "PASS"

    drifted_mark = 120.0
    _record(pf, events, ts=1, action="HOLD", mark=drifted_mark)
    second = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=drifted_mark,
        previous_book=first.book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "PASS"
    assert second.mismatches == ()
    assert second.book.equity == Decimal(str(pf.equity(drifted_mark)))


def test_f2_case4_old_event_corruption_fails() -> None:
    """(F2-4) Corrupción de un evento ANTERIOR al checkpoint ⇒ FAIL.

    El evento viejo corrompido lo rejuega full (diverge) pero no incremental
    (que parte del checkpoint ya validado).
    """
    _, events, mark = _flat_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert first.status == "PASS"
    corrupted = list(events)
    assert corrupted[0].fee == 0.1
    corrupted[0] = replace(corrupted[0], fee=50.0)
    second = reconcile_with_book(
        corrupted,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=first.book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "FAIL"
    assert second.accounting_residual != Decimal("0")


def test_f2_case5_new_event_corruption_fails() -> None:
    """(F2-5) Corrupción de un evento POSTERIOR al checkpoint ⇒ FAIL.

    El evento nuevo corrompido lo rejuegan full e incremental por igual, pero la
    equity reconstruida diverge de la equity live persistida por el engine real.
    """
    pf, events, mark = _open_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert first.status == "PASS"

    _record(pf, events, ts=2, action="BUY", mark=mark, exec_price=105.0, quantity=1.0, fee=0.2)
    _record(pf, events, ts=3, action="HOLD", mark=mark)  # último evento: equity live real
    live_events = list(events)
    corrupted_buy = replace(live_events[1], fee=live_events[1].fee + 50.0)
    new_events = [live_events[0], corrupted_buy, live_events[2]]
    second = reconcile_with_book(
        new_events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=first.book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "FAIL"
    assert second.accounting_residual != Decimal("0")
    assert "equity" in second.mismatches


def test_f2_case6_deleted_event_fails() -> None:
    """(F2-6) Evento borrado ⇒ FAIL (full no lo ve, incremental parte del checkpoint)."""
    _, events, mark = _flat_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert first.status == "PASS"
    deleted = events[:1]  # desaparece el SELL que cerró la posición
    second = reconcile_with_book(
        deleted,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=first.book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "FAIL"
    assert second.accounting_residual != Decimal("0")


def test_f2_case7_compensating_corruption_fails() -> None:
    """(F2-7) Corrupción compensada de eventos viejos ⇒ FAIL por componentes.

    Fee↑ + price/qty↓ que conservan la equity final bit-igual (100009.9): full
    (corrupto) vs incremental (checkpoint bueno) divergen en cash/pos/fees/avg.
    """
    pf, events, mark = _open_capital()
    book = _book_from_portfolio(pf, mark=mark, cursor_ts=0)
    good_equity = float(book.equity)
    corrupted = [
        _make_event(
            ts=0,
            session="recon-book",
            action="BUY",
            filled=True,
            exec_price=80.0,
            quantity=0.5,
            fee=5.1,
            equity=good_equity,
        ),
        _make_event(
            ts=1,
            session="recon-book",
            action="HOLD",
            filled=False,
            exec_price=None,
            quantity=None,
            fee=0.0,
            equity=good_equity,
        ),
    ]
    result = reconcile_with_book(
        corrupted,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=book.to_dict(),
        interval_ms=_INTERVAL_MS,
    )
    assert result.status == "FAIL"
    assert result.accounting_residual != Decimal("0")
    assert "equity" not in result.mismatches
    assert "cash" in result.mismatches
    assert "position_qty" in result.mismatches
    assert "fees" in result.mismatches


def test_f2_case8_restart_with_new_fills_passes_and_advances() -> None:
    """(F2-8) Restart + fills nuevos: checkpoint recargado de un estado serializado.

    Se serializa el checkpoint (to_dict) y se recarga (from_dict) simulando el
    restart; luego un round-trip legítimo tras el cursor ⇒ PASS y avanza.
    """
    pf, events, mark = _open_capital()
    first = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=None,
        interval_ms=_INTERVAL_MS,
    )
    assert first.status == "PASS"
    reloaded = BookState.from_dict(first.book.to_dict())
    assert reloaded == first.book  # el estado serializado recarga bit-exacto

    _record(pf, events, ts=3, action="SELL", mark=mark, exec_price=120.0, quantity=1.0, fee=0.2)
    _record(pf, events, ts=4, action="HOLD", mark=mark)
    assert pf.position == 0.0  # cierre completo
    second = reconcile_with_book(
        events,
        initial_capital=_CAPITAL,
        mark_price=mark,
        previous_book=first.book.to_dict(),  # reloaded desde disco
        interval_ms=_INTERVAL_MS,
    )
    assert second.status == "PASS"
    assert second.mismatches == ()
    assert second.book.last_event_ms == 4
    first_cursor = first.book.last_event_ms
    second_cursor = second.book.last_event_ms
    assert first_cursor is not None and second_cursor is not None
    assert second_cursor > first_cursor
    assert second.book.realized_pnl == Decimal(str(pf.realized_pnl))
    assert second.book.fees == Decimal(str(pf.total_fees))


def test_book_state_roundtrip() -> None:
    """to_dict → from_dict conserva el estado exacto (valores str(Decimal) + cursor)."""
    original = BookState(
        cash=Decimal("99899.9"),
        position_qty=Decimal("1.0"),
        average_entry=Decimal("100.0"),
        realized_pnl=Decimal("0"),
        fees=Decimal("0.1"),
        equity=Decimal("100009.9"),
        entry_fees=Decimal("0.1"),
        last_event_ms=1_700_000_000_000,
    )
    assert BookState.from_dict(original.to_dict()) == original

    flat = BookState(
        cash=Decimal("100019.78"),
        position_qty=Decimal("0"),
        average_entry=None,
        realized_pnl=Decimal("19.78"),
        fees=Decimal("0.22"),
        equity=Decimal("100019.78"),
        entry_fees=Decimal("0.0"),
        last_event_ms=None,
    )
    assert BookState.from_dict(flat.to_dict()) == flat

    # Tolerancia: falta una clave esencial ⇒ None (no crash).
    partial = dict(flat.to_dict())
    del partial["cash"]
    assert BookState.from_dict(partial) is None

    # Tolerancia del cursor: serialización previa sin last_event_ms ⇒ checkpoint
    # parseable pero sin cursor usable (re-baseline documentado; nada desplegado).
    legacy_components = {k: v for k, v in flat.to_dict().items() if k != "last_event_ms"}
    assert legacy_components["average_entry"] == ""
    parsed = BookState.from_dict(legacy_components)
    assert parsed is not None
    assert parsed.last_event_ms is None
