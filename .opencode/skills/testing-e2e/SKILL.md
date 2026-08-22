---
name: testing-e2e
description: Usar cuando haya que validar el flujo completo del sistema de punta a punta automatizado (market→features→decision→risk→paper→outcome→reflection→memory→API), cubriendo happy paths, fallos y edge cases (PRD §73)
---

# testing-e2e — E2E 100% automatizados

## Propósito

Un E2E mínimo recorre TODO el pipeline del agente sobre entradas controladas y verifica el resultado final observable (API/DB), sin intervención humana. Deben cubrirse happy path, fallos y edge cases.

## Cuándo usar

- Al cerrar fases con flujo completo (Fase 06 backtest, Fase 10 risk+paper, Fase 11 reflection loop).
- Antes de gates de fase cuyo DoD exige "E2E PASS".
- Regresión de release candidate (Fase 15).

**Cuándo NO:** validar una función aislada o una integración puntual.

## Entradas → Salidas

- **Entradas:** escenario definido (dataset replay congelado o eventos sintéticos), entorno levantado (docker compose), fake/stub de LLM con respuestas grabadas.
- **Salidas:** suite e2e verde automatizable en CI + evidencia; reporte de escenario.

## Escenarios mínimos por fase (patrón)

1. **Happy path:** vela confirmada → features → decisión BUY válida → riesgo OK → paper fill → trade → outcome → reflexión → memoria → visible en API/dashboard.
2. **Fallos:** LLM timeout/devuelve inválido → HOLD sin romper ciclo; market STALE bloquea nuevas posiciones; presupuesto agotado bloquea llamadas.
3. **Edge cases:** SELL sin posición (rechazado); señal durante kill switch activo; doble vela simultánea multi-timeframe.

## Convenciones del proyecto

- Marcador `@pytest.mark.e2e`; ejecución: `uv run pytest -m e2e`.
- Determinismo: dataset congelado + seeds + LLM cacheado/grabado ⇒ mismo resultado siempre.
- Sin red externa en CI: todo evento de mercado viene de fixtures/replay.
- Aserciones sobre estados finales persistidos (DB/API), no sobre logs.

## Checklist de escenario

1. Precondiciones automatizadas (compose up + migraciones + seed).
2. Ejecución del flujo completo en un proceso/test coherente.
3. Verificación de cada frontera clave (decisión registrada, fill correcto, PnL neto esperado, memoria insertada con timestamps correctos).
4. Teardown limpio.
5. Evidencia + referencia en reporte de fase §16.

## Errores comunes

- E2E "que duerme" con sleeps fijos en vez de esperar condiciones.
- Depender del LLM real: costoso y no determinista (prohibido en CI).
- Cubrir solo el happy path.

## Referencias

- PRD §73. Skills: testing-integration, data-leakage (timestamps), gestion-evidencias.
