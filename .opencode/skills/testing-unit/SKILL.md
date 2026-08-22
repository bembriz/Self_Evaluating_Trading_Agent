---
name: testing-unit
description: Usar al implementar cualquier función/clase del producto que deba llevar unit tests, cuando se configuren gates de cobertura ≥90%, o cuando módulos críticos exijan 100% branch coverage (PRD §70-71)
---

# testing-unit — Unit tests con cobertura exigente

## Propósito

Unit tests rápidos, aislados y deterministas del dominio puro, con gate global ≥90% y objetivo 100% branch en módulos críticos. Metodología base: **superpowers:test-driven-development** (obligatoria).

## Cuándo usar

- Cualquier lógica de dominio: indicadores (RSI/MACD/ATR), PnL, fees, slippage, sizing, risk rules, stop-loss/take-profit, memory filtering, validación LLM, transiciones portfolio.
- Al configurar CI/cobertura por primera vez (Fase 01).

**Cuándo NO:** integración real con DB/API (→ testing-integration); flujo completo (→ testing-e2e).

## Entradas → Salidas

- **Entradas:** unidad a implementar (TDD: primero el test), fixtures mínimos.
- **Salidas:** suite verde + `coverage.json` en evidencia de fase + registro vía evidence.sh.

## Convenciones del proyecto

```bash
# Suite estándar del producto (Fase 01+)
uv run pytest --cov=src --cov-branch --cov-fail-under=90
# Arnés
uv run pytest harness/tests --cov=harness/scripts --cov-fail-under=80
```

- Marcadores pytest: `@pytest.mark.unit` (reservar integration/e2e para sus skills).
- Fixtures ejemplo disponibles bajo convención `tests/fixtures/` (mensajes WS grabados, salidas LLM JSON).
- Módulos críticos 100% branch: risk engine, portfolio accounting, sizing, kill switch, LIVE activation, mode transition, leakage guards (PRD §70).
- Tests deterministas: sin red, sin tiempo real (usa inyección/relojes), seeds fijos.

## Checklist por unidad

1. RED: test que falla describiendo comportamiento esperado.
2. GREEN: implementación mínima.
3. REFACTOR con calidad (code-quality).
4. Casos borde: cero, vacío, máximo, negativo, inválido.
5. Branch coverage del módulo crítico revisada en coverage.json.
6. Evidencia registrada.

## Errores comunes

- Testear mocks en vez de comportamiento.
- Tests dependientes de orden o estado global.
- "Subir" cobertura con tests triviales sin aserciones reales.

## Referencias

- superpowers:test-driven-development (metodología), code-quality, gestion-evidencias.
