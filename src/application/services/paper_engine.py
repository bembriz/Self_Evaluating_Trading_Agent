"""Paper Trading Engine (PRD §25): datos reales, ejecución simulada local.

Simula órdenes/fills/fees/slippage/balances/posiciones/PnL de forma determinista
sobre datos históricos congelados. El Risk Engine (dominio) valida CADA evento;
los stops/TP/trailing tienen prioridad absoluta sobre la intención del LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.portfolio.portfolio import Portfolio
from domain.risk.config import RiskConfig
from domain.risk.engine import PortfolioRiskState, RiskEngine, TradeProposal
from domain.risk.guards import KillSwitch
from domain.risk.stops import update_trailing
from domain.trading.decision import TradingDecision
from domain.trading.fees import FeeModel
from domain.trading.fill import Fill
from domain.trading.signal import Action
from domain.trading.slippage import SlippageModel


@dataclass(frozen=True, slots=True)
class PaperPosition:
    """Posición abierta del paper engine con su gestión de salida."""

    quantity: float
    entry_price: float
    stop_loss: float
    take_profit: float | None
    highest_price: float
    entry_ts: int


@dataclass(frozen=True, slots=True)
class PaperEvent:
    """Resultado de procesar un tick precio+decisión."""

    filled: bool
    action: Action
    exit_reason: str = ""
    risk_reason: str = ""
    fill: Fill | None = None


class PaperEngine:
    """Motor de paper trading determinista gobernado por el Risk Engine."""

    def __init__(
        self,
        *,
        config: RiskConfig,
        fee_model: FeeModel | None = None,
        slippage_model: SlippageModel | None = None,
    ) -> None:
        self._config = config
        self._engine = RiskEngine(config)
        self._fees = fee_model or FeeModel()
        self._slippage = slippage_model or SlippageModel()
        self.portfolio = Portfolio(initial_cash=config.capital, cash=config.capital)
        self._kill_switch = KillSwitch()
        self._position: PaperPosition | None = None
        self._realized_pnl_today = 0.0
        self._peak_equity = config.capital
        self._last_price: float | None = None
        self._last_atr = 0.0

    @property
    def position(self) -> PaperPosition | None:
        return self._position

    @property
    def realized_pnl_today(self) -> float:
        return self._realized_pnl_today

    @property
    def peak_equity(self) -> float:
        return max(self._peak_equity, self.portfolio.equity(self._last_price or 0.0))

    def attach_kill_switch(self, kill_switch: KillSwitch) -> None:
        """Inyecta un estado externo persistente (SystemState) del kill switch."""
        self._kill_switch = kill_switch

    def mark_to_market(self, *, price: float) -> float:
        """Actualiza el pico de equity marcando la posición a mercado."""
        equity = self.portfolio.equity(price)
        if equity > self._peak_equity:
            self._peak_equity = equity
        return equity

    def on_price(
        self, *, decision: TradingDecision, price: float, atr: float | None, timestamp_ms: int
    ) -> PaperEvent:
        """Punto único de entrada: stop→TP→trailing primero; luego la decisión."""
        self._last_price = price
        self._last_atr = atr or 0.0
        # 1. Prioridad absoluta: gestión de la posición abierta.
        if self._position is not None:
            exit_event = self._check_exits(price=price, timestamp_ms=timestamp_ms)
            if exit_event is not None:
                return exit_event

        # 2. La intención del LLM pasa por el Risk Engine.
        proposal = TradeProposal(
            action=decision.action,
            intensity=decision.intensity,
            price=price,
            atr=atr,
            timestamp_ms=timestamp_ms,
        )
        state = PortfolioRiskState(
            open_positions=1 if self._position is not None else 0,
            realized_pnl_today=self._realized_pnl_today,
            peak_equity=self._peak_equity,
            equity=self.mark_to_market(price=price),
            kill_switch=self._kill_switch.state,
        )
        verdict = self._engine.evaluate(proposal, state)

        if not verdict.approved:
            return PaperEvent(filled=False, action=decision.action, risk_reason=verdict.reason)
        if decision.action is Action.HOLD:
            return PaperEvent(filled=False, action=Action.HOLD)
        if decision.action is Action.SELL and self._position is not None:
            return self._close_position(price=price, timestamp_ms=timestamp_ms, reason="llm_sell")
        if decision.action is Action.BUY and verdict.size is not None:
            return self._open_position(
                size_quantity=verdict.size.quantity,
                price=price,
                stop=verdict.stop_loss or price * (1.0 - 1e-9),
                target=verdict.take_profit,
                timestamp_ms=timestamp_ms,
            )
        return PaperEvent(filled=False, action=decision.action)

    # ------------------------------------------------------------------ exits

    def _check_exits(self, *, price: float, timestamp_ms: int) -> PaperEvent | None:
        pos = self._position
        if pos is None:
            return None
        highest = max(pos.highest_price, price)
        new_stop = update_trailing(
            current_stop=pos.stop_loss,
            highest_price=highest,
            atr=self._last_atr,
            config=self._config,
        )
        pos = PaperPosition(
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            stop_loss=new_stop,
            take_profit=pos.take_profit,
            highest_price=highest,
            entry_ts=pos.entry_ts,
        )
        self._position = pos
        if price <= pos.stop_loss:
            # Stop por encima de la entrada ⇒ protección de beneficios (trailing).
            reason = "trailing_stop" if pos.stop_loss > pos.entry_price else "stop_loss"
            return self._close_position(price=price, timestamp_ms=timestamp_ms, reason=reason)
        if pos.take_profit is not None and price >= pos.take_profit:
            return self._close_position(
                price=price, timestamp_ms=timestamp_ms, reason="take_profit"
            )
        return None

    def _close_position(self, *, price: float, timestamp_ms: int, reason: str) -> PaperEvent:
        assert self._position is not None
        fill = self._make_fill(
            action=Action.SELL,
            price=price,
            quantity=self._position.quantity,
            timestamp_ms=timestamp_ms,
        )
        before = self.portfolio.realized_pnl
        self.portfolio.apply_sell(fill)
        self._realized_pnl_today += self.portfolio.realized_pnl - before
        self._mark_peak_if_needed(fill.exec_price)
        self._position = None
        return PaperEvent(filled=True, action=Action.SELL, exit_reason=reason, fill=fill)

    def _open_position(
        self,
        *,
        size_quantity: float,
        price: float,
        stop: float,
        target: float | None,
        timestamp_ms: int,
    ) -> PaperEvent:
        exec_price = price * (1.0 + self._slippage.rate)
        notional = size_quantity * exec_price
        fee = self._fees.fee(notional)
        total_cost = notional + fee
        cash = self.portfolio.cash
        if total_cost > cash + 1e-9:
            size_quantity = (cash / 1.001) / exec_price  # ajusta al cash disponible
            notional = size_quantity * exec_price
            fee = self._fees.fee(notional)
        fill = Fill(
            timestamp_ms=timestamp_ms,
            action=Action.BUY,
            price=price,
            exec_price=exec_price,
            quantity=size_quantity,
            notional=notional,
            fee=fee,
            slippage_cost=size_quantity * (exec_price - price),
        )
        self.portfolio.apply_buy(fill)
        self._position = PaperPosition(
            quantity=size_quantity,
            entry_price=fill.exec_price,
            stop_loss=stop,
            take_profit=target,
            highest_price=fill.exec_price,
            entry_ts=timestamp_ms,
        )
        self._mark_peak_if_needed(fill.exec_price)
        return PaperEvent(filled=True, action=Action.BUY, fill=fill)

    def _make_fill(
        self, *, action: Action, price: float, quantity: float, timestamp_ms: int
    ) -> Fill:
        rate = self._slippage.rate
        sign = -1.0 if action is Action.SELL else 1.0
        exec_price = price * (1.0 + sign * rate)
        notional = quantity * exec_price
        fee = self._fees.fee(notional)
        slip_cost = quantity * abs(exec_price - price)
        return Fill(
            timestamp_ms=timestamp_ms,
            action=action,
            price=price,
            exec_price=exec_price,
            quantity=quantity,
            notional=notional,
            fee=fee,
            slippage_cost=slip_cost,
        )

    def _mark_peak_if_needed(self, price: float) -> None:
        equity = self.portfolio.equity(price)
        if equity > self._peak_equity:
            self._peak_equity = equity
