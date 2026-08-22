---
name: risk-engine
description: Usar al implementar o modificar el Risk Engine determinista, sizing, stops, límites de portfolio, kill switch, o cualquier transición de modo (paper→testnet→live) — el LLM jamás toca estas reglas (PRD §21-24, §49-51)
---

# risk-engine — Autoridad absoluta sobre el riesgo

## Propósito

Motor DETERMINISTA con autoridad final: valida/rechaza decisiones, dimensiona posiciones, aplica stops y protege capital. Prioridad: preservar capital > evitar trades inválidos > rentabilidad (PRD §86).

## Cuándo usar

- Implementar reglas: max_position_allocation 2%, max_daily_loss 2%, max_drawdown 5%, max_open_positions 1, leverage 0, stop_loss_required.
- Sizing híbrido: intensity del LLM (LOW/MEDIUM/HIGH) → monto real vía risk budget + ATR + stop distance + capital + drawdown.
- Stops/TP/trailing/max-time-in-position basados en ATR+volatilidad.
- Kill switch en dominio/API/CLI/dashboard: activación bloquea nuevas órdenes, evento auditado, recuperación solo humana.
- Transición LIVE: exige TRADING_MODE=LIVE ∧ LIVE_TRADING_ENABLED ∧ LIVE_READINESS_GATE=PASSED ∧ USER_APPROVAL; tras reinicio vuelve a DISABLED.

**Cuándo NUNCA:** permitir que salida del LLM modifique parámetros, omita stops o habilite LIVE.

## Invariantes testables (objetivo 100% branch)

1. Toda orden pasa por RiskGate; sin excepciones ni bypass.
2. Rechazo ⇒ razón registrada (`risk_evaluations`) + métrica `failed_risk_validations`.
3. STOP LOSS / TAKE PROFIT / TRAILING / MAX_DD / KILL SWITCH preceden a cualquier intención del LLM.
4. Parámetros versionados en `risk_configs`; cambios = nueva versión + aprobación humana.
5. Kill switch persistente entre reinicios hasta reset humano.

## Checklist de cambio en risk

1. Regla expresada como función pura testeable.
2. Unit tests 100% branch (caso límite incluido: exactamente en umbral).
3. E2E que demuestre prioridad de stops sobre decisión LLM.
4. Auditoría de eventos generada.
5. Si cambia defaults: ADR + nueva versión de config.

## Errores comunes

- Confiar en el LLM para sizing cuantitativo (solo emite intensidad).
- Kill switch solo en UI sin capa dominio.
- Drawdown calculado sobre equity no marcada a mercado.

## Referencias

- PRD §21–24, §47, §49–51, §86. Skills: backtesting, data-leakage, testing-unit.
