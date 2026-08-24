# Commit Candidate Report — 2026-08-23 (Fase 05)

> Obligatorio antes de pedir autorización de `git commit` (PRD §65-66).

## Objetivo

Fase 05 (Feature Engine & Market State): indicadores técnicos puros en stdlib (EMA/SMA/RSI/MACD/ATR/VWAP/returns/vol/momentum/rel-vol), clasificador de régimen determinista versionado (`regime-v1`), y ensamblado de `MarketState` multi-timeframe (15m/1h/4h) con contexto BTC y order book. Todo causal, con tests anti-lookahead. Sin dependencias nuevas (ADR-0002).

## Rama

| Campo | Valor |
|---|---|
| branch | main |
| base commit | c24b86e docs(readme): actualizar estado de fases 03 y 04 |

## Archivos

- **Creados (18):** dominio `src/domain/market/{indicators,regime,state,feature_engine}.py`; tests `tests/{test_indicators,test_regime,test_feature_engine,test_no_lookahead}.py`; `docs/adr/ADR-0002-feature-engine-pure-python.md`; `docs/phases/05/*` (evidence + commit-candidate); `docs/phases/phase-05-report.md`; `docs/uat/phase-05-uat.md`; plan.
- **Modificados (1):** `harness/state/progress.yaml`.
- **Eliminados:** ninguno.

## Diff

```bash
git diff --cached --stat  # 19 archivos · 1779 insertions(+), 14 deletions(-)
```

## Arquitectura afectada

Nuevo plano de Feature Engine en dominio puro: `indicators.py` (funciones causales) y `regime.py` (`RegimeClassifier` v1) son consumidos por `feature_engine.py` (`FeatureEngine.compute_state`) que produce `state.py` (`MarketState`, `TimeframeFeatures`, `BtcContext`). Sin cambios en dominio existente, API HTTP, migraciones ni infraestructura. **Blast radius (codebase-memory-mcp `detect_changes`):** 4 seed symbols (módulos nuevos) · **impacted_total=0** — ningún código de producción existente consume estos módulos (solo sus tests).

## Índice del grafo

- [ ] Índice re-indexado tras el commit (`index_repository`) — pendiente (grafo actual es pre-Fase-05).
- [ ] Cobertura verificada sobre archivos tocados (`check_index_coverage`) — tras re-indexar.

## Tests ejecutados

| Suite | Resultado | Evidencia |
|---|---|---|
| Unit | 128 passed | docs/phases/05/evidence/unit-tests.log |

## Cobertura

**94.84%** línea / **95%** branch — gate ≥90%. Módulos Fase 05 (`indicators`, `regime`, `feature_engine`, `state`) al **100%** branch. `docs/phases/05/evidence/coverage.json`.

## Calidad

```bash
uv run ruff check .             # All checks passed
uv run ruff format --check .    # 109 files already formatted
uv run mypy src tests           # Success: no issues found (strict)
uv run pytest                   # 128 passed
```

## Seguridad

- [x] Sin secretos en el diff (grep api_key/secret/token/password/PRIVATE KEY → 0)
- [x] Sin .env ni credenciales (dominio puro, sin I/O)
- [x] Sin red ni lectura de configuración sensible

## Riesgos

- `float` IEEE-754 para indicadores: suficiente para features de decisión; la contabilidad PnL usará el mecanismo que decida Fase 06 (documentado en ADR-0002).
- VWAP "de sesión" acumulado sobre la serie recibida: el límite de sesión lo define el llamador.

## Deuda técnica

Ninguna nueva. Warmup explícito con `None` (elección deliberada, no deuda).

## Mensaje de commit propuesto

```
feat(phase-05): Feature Engine & Market State

- indicadores técnicos puros en stdlib (EMA/SMA/RSI/MACD/ATR/VWAP/returns/vol/momentum/rel-vol)
- clasificador de régimen determinista versionado (regime-v1) + RegimeConfig
- MarketState multi-timeframe (15m/1h/4h) + contexto BTC de solo lectura + order book
- FeatureEngine puro y causal (sin lookahead) · ADR-0002 · 128 tests · cobertura 94.84%
```

---

**DECISIÓN DEL USUARIO:** ☐ APPROVED → ejecutar commit ☐ REJECTED — Fecha/comentario:
