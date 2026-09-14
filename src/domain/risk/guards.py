"""Guards de protección de capital (PRD §22): daily loss, drawdown, kill switch.

El kill switch vive en dominio (no solo en UI): su estado es serializable para
persistirlo en SystemState y sobrevivir reinicios hasta reset humano (PRD §50).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from domain.risk.config import RiskConfig


def daily_loss_exceeded(realized_pnl_today: float, *, capital: float, config: RiskConfig) -> bool:
    """True si la pérdida realizada de hoy toca o supera el límite diario."""
    return realized_pnl_today <= -(capital * config.max_daily_loss)


def drawdown_exceeded(*, peak_equity: float, equity: float, config: RiskConfig) -> bool:
    """True si el drawdown desde el pico de equity toca o supera el máximo."""
    if peak_equity <= 0.0:
        return False
    if equity > peak_equity:
        return False
    return (peak_equity - equity) / peak_equity >= config.max_drawdown


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    """Estado serializable del kill switch."""

    active: bool = False
    reason: str = ""
    activated_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "reason": self.reason,
            "activated_at_ms": self.activated_at_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KillSwitchState:
        return cls(
            active=bool(data.get("active", False)),
            reason=str(data.get("reason", "")),
            activated_at_ms=int(data.get("activated_at_ms", 0)),
        )


class KillSwitch:
    """Interruptor de emergencia: bloquea órdenes hasta reset humano explícito."""

    def __init__(self, initial_state: KillSwitchState | None = None) -> None:
        self._state = initial_state or KillSwitchState()

    @property
    def state(self) -> KillSwitchState:
        """Estado actual (para persistir y restaurar entre reinicios)."""
        return self._state

    def allows_trading(self) -> bool:
        return not self._state.active

    def activate(self, *, reason: str, timestamp_ms: int) -> KillSwitchState:
        """Activa el switch. Idempotente: conserva la primera razón/timestamp."""
        if not self._state.active:
            self._state = KillSwitchState(active=True, reason=reason, activated_at_ms=timestamp_ms)
        return self._state

    def activate_and_return(self) -> KillSwitch:
        self.activate(reason="test", timestamp_ms=0)
        return self

    def reset(
        self,
        *,
        by: Literal["human", "llm"],
        approval_id: str = "",
    ) -> None:
        """Solo un reset humano con identificación de aprobación lo desactiva."""
        if by != "human" or not approval_id:
            raise PermissionError("el kill switch solo puede resetearse por aprobación humana")
        self._state = KillSwitchState(active=False)
