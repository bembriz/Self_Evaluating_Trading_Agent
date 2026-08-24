# Reporte de Fase 05 — Feature Engine & Market State

**Fecha:** 2026-08-23
**Estado de fase:** in_progress
**Avance fase:** 90.0% · **Avance global:** 31.05%
**Gate:** pending

---

## 1. Executive Summary

Se implementó el Feature Engine como dominio puro (PRD §15–16): indicadores técnicos (EMA, SMA, RSI, MACD, ATR, VWAP, returns, volatilidad realizada, momentum, volumen relativo) en Python stdlib sin dependencias nuevas, un clasificador de régimen determinista y versionado (`regime-v1`), y el ensamblado de un `MarketState` inmutable multi-timeframe (15m/1h/4h) que integra order book, contexto BTC de solo lectura y régimen. Todo causal (sin lookahead), verificado con tests anti-lookahead dedicados. 128 tests, cobertura 94.84% (nuevos módulos a 100%), lint/typing/format verdes. ADR-0002 documenta la decisión pure-Python.

## 2. Objetivo

Transformar candles multi-timeframe + order book + contexto BTC en un `MarketState` estructurado con régimen de mercado determinista, sin introducir dependencias de indicadores y con garantía de no-lookahead (PRD §15–16, §34, Fase 05).

## 3. Scope

- `indicators.py`: EMA/SMA/RSI/MACD/ATR/VWAP/returns/realized volatility/momentum/relative volume, causales, con warmup explícito (`None`).
- `regime.py`: `MarketRegime` + `RegimeClassifier` (v1) + `RegimeConfig` frozen.
- `state.py`: `TimeframeFeatures`, `BtcContext`, `MarketState` (frozen).
- `feature_engine.py`: `FeatureEngine` + `FeatureEngineConfig`; ensambla `MarketState`.
- Tests unitarios + tests anti-lookahead (corruptor temporal + replay truncado).
- ADR-0002.

## 4. Out of Scope

Consumo del `MarketState` por baselines/Decision Agent (Fase 06/08). Persistencia de features de orden book en tiempo real (ya en Fase 04). Backtesting, ML, LLM, riesgo, ejecución. Endpoints HTTP (Fase 13). No se añaden migraciones ni dependencias.

## 5. Arquitectura antes/después

**Antes:** dominio con `Candle`/`OrderBook`/`OrderBookFeatureSnapshot`/eventos de stream; sin indicadores ni estado agregado.
**Después:** capa de Feature Engine pura en `domain/market/` (`indicators`, `regime`, `state`, `feature_engine`), sin I/O. El flujo lógico PRD §8 (OB/CANDLES → FE → STATE) queda implementado: `FeatureEngine.compute_state()` consume candles por timeframe + snapshot de order book + candles BTC y produce `MarketState`. Regla hexagonal respetada: dominio puro, sin imports de infraestructura.

## 6. Archivos creados

`src/domain/market/{indicators,regime,state,feature_engine}.py`, `tests/{test_indicators,test_regime,test_feature_engine,test_no_lookahead}.py`, `docs/adr/ADR-0002-feature-engine-pure-python.md`, `docs/phases/05/*`, `docs/phases/phase-05-report.md`, `docs/uat/phase-05-uat.md`, `docs/superpowers/plans/2026-08-23-phase-05-feature-engine-market-state.md`.

## 7. Archivos modificados

`harness/state/progress.yaml` (estado Fase 05, entregables, time_log).

## 8. Dependencias

Ninguna nueva (indicadores en stdlib: `math`, `collections.abc`, `dataclasses`, `enum`). Sin Dependency Proposal requerida. Decisión documentada en ADR-0002.

## 9. Configuración

Sin cambios en `config/*.yaml`. Parámetros de features/régimen expuestos como dataclasses frozen (`FeatureEngineConfig`, `RegimeConfig`) con defaults, versionables por experimento.

## 10. Comandos exactos (verificados)

```bash
uv run pytest --cov=src --cov-branch --cov-fail-under=90   # 128 passed · 94.84%
uv run coverage json -o docs/phases/05/evidence/coverage.json
uv run ruff check .                                        # exit 0
uv run ruff format --check .                               # exit 0
uv run mypy src tests                                      # exit 0
```

## 11. Rutas

`src/domain/market/`, `tests/`, `docs/adr/ADR-0002-*.md`, `docs/phases/05/evidence/`, `docs/superpowers/plans/`.

## 12. API endpoints

Ninguno (Fase de dominio puro).

## 13. Migraciones

Ninguna.

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ☑ | 128 passed | `docs/phases/05/evidence/unit-tests.log` |
| Integration | — | n/a (sin I/O en esta fase) | — |
| E2E | — | n/a (sin flujo nuevo end-to-end) | — |

## 15. Coverage

94.84% global (branch 95%). Nuevos módulos `indicators.py`, `regime.py`, `feature_engine.py`, `state.py` al **100%** branch. Fuente: `docs/phases/05/evidence/coverage.json`.

## 16. E2E

No aplica (fase de dominio puro). El flujo completo market→features→estado se ejercita en unit tests (`test_feature_engine.py`); la integración con el worker real llega con el Decision Agent (Fase 08).

## 17. UAT

- Checklist: `docs/uat/phase-05-uat.md`
- Veredicto: PENDIENTE

## 18. Evidencias

Índice completo en `docs/phases/05/evidence/log.md` (lint, typing, format, unit-tests, coverage.json).

## 19. Métricas

- Tests: 128 passed (11 indicadores, 11 régimen, 8 feature engine, 7 anti-lookahead nuevos).
- Cobertura: 94.84% línea / 95% branch; módulos Fase 05 a 100% branch.
- Indicadores: 11 funciones puras, causales, con warmup explícito.

## 20. Logs relevantes

`unit-tests.log`: `128 passed` con `--cov-fail-under=90`. `lint.log`/`typing.log`/`format.log`: `exit=0`.

## 21. Git diff

`git diff --stat`: `harness/state/progress.yaml` (48+/14-). Archivos nuevos listados en §6 (untracked, pendientes de commit autorizado). Commit Candidate Report se generará en el flujo `flujo-commits`.

## 22. Riesgos

- `float` IEEE-754 para indicadores: suficiente para features de decisión; la contabilidad PnL usará el mecanismo que decida Fase 06 (documentado en ADR-0002).
- VWAP "de sesión" acumulado sobre la serie recibida: el límite de sesión lo define el llamador. Mitigación: documentado; el llamador debe segmentar por sesión.

## 23. Seguridad

Sin cambios: sin secretos, sin I/O, sin red. Dominio puro.

## 24. Deuda técnica

Ninguna nueva. Warmup explícito con `None` (elección deliberada, no deuda).

## 25. Known Issues

Ninguno bloqueante. El warning `StarletteDeprecationWarning` (httpx/starlette testclient) es preexistente de fases anteriores.

## 26. Rollback

Eliminar los archivos de `src/domain/market/{indicators,regime,state,feature_engine}.py` y sus tests; revertir `harness/state/progress.yaml`. No hay migraciones ni dependencias que revertir.

## 27. Competencias de Ingeniería de Software practicadas

- **Domain Modeling**: entidades frozen (`MarketState`, `TimeframeFeatures`, `BtcContext`) con invariantes.
- **Numerical Computing**: fórmulas EMA/Wilder/ATR/VWAP en stdlib.
- **Time-Series Engineering**: warmup, causalidad, multi-timeframe, régimen determinista versionado.
- **Testing**: TDD (RED→GREEN→REFACTOR), tests anti-lookahead (corruptor temporal + replay truncado), 100% branch en módulos nuevos.
- **Documentation**: ADR-0002, plan de implementación.

## 28. Definition of Done

- scope complete: 6/6 entregables `done` en ledger ☑
- tests PASS: 128 passed ☑
- coverage ≥90%: 94.84% ☑
- lint green: exit 0 ☑
- typing green: exit 0 ☑
- format green: exit 0 ☑
- evidence complete ☑
- diff reviewed: pendiente de commit autorizado
- UAT approved: pendiente de usuario
- user approved: pendiente

## 29. Estado CI

Pendiente de push remoto (trunk-based; commits requieren autorización). Lint/typing/tests verdes localmente.

## 30. Solicitud de aprobación

- [ ] Presentado al usuario
- **DECISIÓN DEL USUARIO:** ☐ APPROVED ☐ REJECTED
- Comentario:
