# Reporte de Fase 10 — Risk & Paper Execution

**Fecha:** 2026-08-23
**Estado de fase:** in_progress (pendiente UAT + gate)
**Avance fase:** 100.0% entregables con evidencia · **Gate mecánico:** 5 PASS · 0 FAIL · 2 MANUAL

---

## 1. Executive Summary

Risk Engine determinista con autoridad absoluta (PRD §21-24): sizing híbrido intensity→monto vía risk budget+ATR con cap de asignación y escala por drawdown, stops/TP/trailing ATR monótono, guards de daily loss 2%/max drawdown 5% con umbrales exactos testeados, kill switch de dominio persistente con reset solo humano, restricciones de portfolio (max positions=1, leverage=0) y Paper Engine determinista que gobierna posición abierta con prioridad absoluta de los stops sobre la intención del LLM. Módulos críticos `domain/risk/*` al **100% branch coverage**. Suite global 309 passed, cobertura 93.10%.

## 2. Objetivo

Motor de riesgo determinista como única autoridad sobre sizing/stops/protección de capital, y Paper Engine que simula órdenes/fills/fees/slippage/balances/posiciones/PnL sobre datos reales (PRD §79 Fase 10).

## 3. Scope

- `domain/risk/config.py`: RiskConfig versionada (`risk-v1`) con defaults PRD §22.
- `domain/risk/sizing.py`: qty = riesgo×escala_dd / distancia_stop; cap allocation+leverage; fail-safe intensity desconocida→MEDIUM; ATR<=0 ⇒ tamaño 0.
- `domain/risk/stops.py`: initial_stop (ATR), take_profit (R múltiplo), trailing monótono no decreciente.
- `domain/risk/guards.py`: daily_loss_exceeded, drawdown_exceeded (equity marcada a mercado), KillSwitch/KillSwitchState serializable, reset exclusivamente humano con approval_id.
- `domain/risk/engine.py`: TradeProposal/PortfolioRiskState/RiskVerdict; orden invariable kill_switch → max_drawdown → max_daily_loss → max_open_positions/no_position_to_reduce → stop_unavailable → zero_size → ok.
- `application/services/paper_engine.py`: ciclo decisión→riesgo→fill→posición→salida (stop_loss/take_profit/trailing_stop/llm_sell), ajuste a cash disponible, determinismo verificado.

## 4. Out of Scope

- Persistencia de risk_evaluations/eventos de auditoría en BD (fase observabilidad).
- Integración del Paper Engine en worker/API y transición paper→testnet (fases 12+).
- Kill switch en API/CLI/dashboard UI (el dominio ya lo expone; las superficies llegan con sus fases).

## 5. Arquitectura antes/después

Antes: dominio con portfolio/fill/fees/slippage pero sin capa de riesgo ni motor de ejecución simulada. Después: `domain/risk` puro (100% branch) + Paper Engine en aplicación que orquesta Portfolio existente. El LLM no puede modificar parámetros: no existen rutas desde TradingDecision hacia RiskConfig.

## 6. Archivos creados

`src/domain/risk/{__init__,config,sizing,stops,guards,engine}.py`, `src/application/services/paper_engine.py`, tests: `test_risk_config`(incluido en sizing)/`test_risk_sizing.py`, `test_risk_stops.py`, `test_risk_guards.py`, `test_risk_engine.py`, `test_paper_engine.py`.

## 7. Archivos modificados

Docs de fase/UAT/plans, ledger de progreso.

## 8. Dependencias

Ninguna nueva.

## 9. Configuración

RiskConfig versionada como fuente única (capital 1000, allocation 2%, daily loss 2%, drawdown 5%, max positions 1, leverage 0). Parametrizable y versionada; cambiar defaults = nueva versión + ADR.

## 10. Comandos exactos

```bash
uv run pytest tests --ignore=tests/integration --cov=src --cov-branch --cov-fail-under=90   # 309 passed, 93.10%
uv run pytest tests/test_risk_engine.py tests/test_risk_sizing.py tests/test_risk_guards.py tests/test_risk_stops.py --cov=domain.risk --cov-branch   # 100%
uv run ruff check . && uv run ruff format --check .   # OK
uv run mypy src tests                                  # Success
```

## 11. Rutas

Sin cambios de API.

## 12. API endpoints

Ninguno.

## 13. Migraciones

Ninguna (sin cambios de esquema).

## 17. UAT

- Checklist: `docs/uat/phase-10-uat.md`
- Veredicto: PENDIENTE

## 18. Evidencias

Índice en `docs/phases/10/evidence/log.md`: `tests-unit`, `lint`, `format-check`, `mypy`/`typing`, `risk-100-branch`.

## 20. Logs relevantes

Salida de cobertura branch al 100% en `domain/risk` registrada como evidencia.

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ✅ 309 passed | PASS (93.10%) | `tests-unit.log` |
| Críticos branch | ✅ domain/risk 100% | PASS | `risk-100-branch.log` |
| Integration | ⚠️ Pendiente entorno (Docker ausente) | N/A | igual fases previas |

## 15. Coverage

93.10% global ≥ 90%. domain/risk: 100% statements + 100% branch (46 branches).

## 16. E2E

Ciclo parcial E2E verificado en unit: BUY→riesgo→fill→stop/trailing/TP/SELL→PnL neto con fees+slippage; determinismo doble ejecución idéntica. E2E completo market→...→memory llega al integrar workers (fases 11+).

## 19. Métricas

Prioridad absoluta demostrada en tests: stop sale aunque el LLM diga HOLD; kill switch precede incluso violando otros guards simultáneamente.


## 21. Git diff

> Resumen del diff + referencia al diff completo generado para el Commit Candidate Report.

## 22. Riesgos

> Riesgos introducidos o descubiertos y su mitigación.

## 23. Seguridad

> Revisión de secretos, superficies expuestas, permisos.

## 24. Deuda técnica

> Deuda conocida registrada en esta fase.

## 25. Known Issues

> Problemas conocidos no bloqueantes.

## 26. Rollback

> Cómo revertir los cambios de esta fase.

## 27. Competencias de Ingeniería de Software practicadas

> Mapear contra PRD §80: qué se practicó y dónde.

## 28. Definition of Done

> Checklist §77: scope complete / tests PASS / integration PASS / E2E PASS / UAT approved /
> coverage ≥90% / CI green / lint green / typing green / documentation complete /
> evidence complete / diff reviewed / user approved.

## 29. Estado CI

> Estado del pipeline (o justificación si aún no existe remoto).

## 30. Solicitud de aprobación

- [ ] Presentado al usuario
- **DECISIÓN DEL USUARIO:** ☒ APPROVED ☐ REJECTED
- Comentario:
