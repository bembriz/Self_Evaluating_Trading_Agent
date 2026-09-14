"""RiskEngine determinista con autoridad absoluta (PRD §22, §24, §86).

Orden de prioridad invariable: kill switch → max drawdown → daily loss →
restricciones de portfolio → requisitos de stop → sizing. Los stops/TP/trailing
preceden a CUALQUIER intención del LLM; el LLM jamás modifica parámetros.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.risk.config import RiskConfig
from domain.risk.guards import (
    KillSwitchState,
    daily_loss_exceeded,
    drawdown_exceeded,
)
from domain.risk.sizing import PositionSize, compute_position_size
from domain.risk.stops import initial_stop, take_profit
from domain.trading.signal import Action


@dataclass(frozen=True, slots=True)
class TradeProposal:
    """Intención de trading (del LLM u otra estrategia) a validar."""

    action: Action
    intensity: object  # Intensity (LOW/MEDIUM/HIGH); el monto lo fija el motor
    price: float
    atr: float | None
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class PortfolioRiskState:
    """Fotografía del estado de riesgo del portfolio para una evaluación."""

    open_positions: int
    realized_pnl_today: float
    peak_equity: float
    equity: float
    kill_switch: KillSwitchState


@dataclass(frozen=True, slots=True)
class RiskVerdict:
    """Resultado de la validación: aprobar/rechazar con razón auditable."""

    approved: bool
    reason: str
    size: PositionSize | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


class RiskEngine:
    """Puerta obligatoria para toda orden. Sin excepciones ni bypass."""

    def __init__(self, config: RiskConfig) -> None:
        self._config = config

    @property
    def config_version(self) -> str:
        return self._config.version

    def evaluate(self, proposal: TradeProposal, state: PortfolioRiskState) -> RiskVerdict:
        cfg = self._config
        if state.kill_switch.active:
            return self._reject("kill_switch")
        if drawdown_exceeded(peak_equity=state.peak_equity, equity=state.equity, config=cfg):
            return self._reject("max_drawdown")

        if proposal.action is Action.HOLD:
            return RiskVerdict(approved=True, reason="no_op")
        if proposal.action is Action.SELL:
            # Long-only: SELL solo reduce posición existente (reductor de riesgo).
            if state.open_positions == 0:
                return self._reject("no_position_to_reduce")
            return RiskVerdict(approved=True, reason="reduce")

        # Acción BUY: nueva exposición. El límite diario solo aplica aquí.
        if daily_loss_exceeded(state.realized_pnl_today, capital=cfg.capital, config=cfg):
            return self._reject("max_daily_loss")
        if state.open_positions >= cfg.max_open_positions:
            return self._reject("max_open_positions")
        if cfg.stop_loss_required and (proposal.atr is None or proposal.atr <= 0.0):
            return self._reject("stop_unavailable")

        drawdown = _current_drawdown(state.peak_equity, state.equity)
        atr = proposal.atr or 0.0
        if atr <= 0.0:
            # Stop no requerido y sin ATR: sizing por asignación máxima, sin stops.
            max_notional = min(
                cfg.max_position_allocation * cfg.capital,
                cfg.capital * (1.0 - cfg.leverage),
            )
            quantity = max_notional / proposal.price if proposal.price > 0 else 0.0
            if quantity <= 0.0:
                return self._reject("zero_size")
            size = PositionSize(
                quantity=quantity,
                notional=max_notional,
                stop_distance=0.0,
                risk_amount=0.0,
                capped=True,
            )
            return RiskVerdict(approved=True, reason="ok_unstopped", size=size)

        size = compute_position_size(
            intensity=proposal.intensity,
            atr=atr,
            price=proposal.price,
            current_drawdown=drawdown,
            config=cfg,
        )
        if size.quantity <= 0.0:
            return self._reject("zero_size")

        stop = initial_stop(entry_price=proposal.price, atr=atr, config=cfg)
        target = take_profit(entry_price=proposal.price, stop_loss=stop, config=cfg)
        return RiskVerdict(
            approved=True, reason="ok", size=size, stop_loss=stop, take_profit=target
        )

    @staticmethod
    def _reject(reason: str) -> RiskVerdict:
        return RiskVerdict(approved=False, reason=reason)


def _current_drawdown(peak_equity: float, equity: float) -> float:
    if peak_equity <= 0.0 or equity >= peak_equity:
        return 0.0
    return (peak_equity - equity) / peak_equity
