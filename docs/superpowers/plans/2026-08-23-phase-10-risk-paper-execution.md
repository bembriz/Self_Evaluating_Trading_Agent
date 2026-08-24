# Fase 10 — Risk & Paper Execution: Plan de Implementación

> Ejecución en línea por el controlador. Módulos críticos: objetivo 100% branch
> en `domain/risk/*` (PRD §70-71). El LLM jamás modifica parámetros de riesgo.

**Goal:** Risk Engine determinista con autoridad absoluta (sizing híbrido intensity→monto,
stops ATR/TP/trailing, límites portfolio/daily-loss/drawdown, kill switch persistente)
y Paper Engine determinista sobre Portfolio existente (PRD §21-25).

## Global Constraints

- Defaults PRD §22: capital=1000, max_position_allocation=2%, max_daily_loss=2%,
  max_drawdown=5%, max_open_positions=1, leverage=0, stop_loss_required=true.
- Prioridad absoluta (PRD §24): KILL SWITCH → MAX_DD → DAILY_LOSS → restricciones portfolio → intención LLM.
- Rechazo ⇒ razón registrada; parámetros versionados (`risk-v1`); kill switch solo reset humano.
- Reutilizar `Portfolio`, `Fill`, `FeeModel`, `SlippageModel`, `Action`/`Intensity`, `TradingDecision`.
- Dominio puro; Paper Engine en `application/services`.

## Tasks

### Task A: RiskConfig versionada + sizing híbrido
- Create: `src/domain/risk/config.py`, `src/domain/risk/sizing.py`
- Test: `tests/test_risk_config.py`, `tests/test_risk_sizing.py`
- Sizing: risk_budget(intensity) → riesgo USD; qty = riesgo/(mult_atr*ATR); cap por allocation y leverage=0; dd escala a la baja; ATR<=0 ⇒ tamaño 0.

### Task B: Stops ATR + TP + trailing
- Create: `src/domain/risk/stops.py`
- Test: `tests/test_risk_stops.py`
- initial_stop(entry, atr), take_profit(R múltiplo), update_trailing monótono no decreciente.

### Task C: Guards daily loss / drawdown / kill switch
- Create: `src/domain/risk/guards.py`
- Test: `tests/test_risk_guards.py` (umbrales exactos incluidos)

### Task D: RiskEngine evaluador (orden de prioridad)
- Create: `src/domain/risk/engine.py` (TradeProposal, PortfolioRiskState, RiskVerdict)
- Test: `tests/test_risk_engine.py` — TODAS las ramas: kill/dd/daily/max-pos/stop-required/sizing-cap/HOLD/SELL-reduce-only/umbral exacto.

### Task E: Paper Engine determinista
- Create: `src/application/services/paper_engine.py`
- Test: `tests/test_paper_engine.py`: ciclo completo decisión→riesgo→fill→posición→salida por stop/TP/trailing/SELL LLM; determinismo (misma secuencia ⇒ mismo resultado); kill switch bloquea; PnL neto con fees+slippage.
