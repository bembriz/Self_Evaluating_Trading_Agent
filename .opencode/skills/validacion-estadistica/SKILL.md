---
name: validacion-estadistica
description: Usar al aplicar análisis estadístico a resultados de trading — bootstrap, Monte Carlo, intervalos de confianza, sensibilidad a fees/slippage/parámetros, detección de overfitting, o al evaluar el gate estadístico para LIVE (PRD §47)
---

# validacion-estadistica — Evidencia estadística, no anécdotas

## Propósito

Convertir resultados de backtest/paper en conclusiones con incertidumbre cuantificada. Un resultado positivo sin distribución ni robustez NO es evidencia.

## Cuándo usar

- Fase 14 (robustness) y gate estadístico de LIVE (§47).
- Al comparar dos estrategias (¿la diferencia es significativa?).
- Sensibilidades: fees, slippage, parámetros.
- Análisis de overfitting y estabilidad por regímenes/ventanas.

**Cuándo NO:** generación de trades (backtesting); diseño de ventanas (walk-forward-validacion).

## Herramientas mínimas obligatorias (PRD §47)

| Análisis | Pregunta que responde |
|---|---|
| Bootstrap sobre trades | IC del expectancy/PnL neto |
| Monte Carlo (permuta/secuencia) | Distribución de drawdowns y riesgo de ruina |
| Intervalos de confianza | ¿Sharpe>1.2 es robusto o suerte? |
| Estabilidad por ventanas/regímenes | ¿Funciona en ≥2 regímenes? |
| Sensibilidad fees/slippage | ¿Sobrevive a costos peores? |
| Sensibilidad parámetros | ¿Vecindario rentable o pico estrecho? |
| Degradación train→val→holdout | ¿Overfitting? |

## Gate estadístico LIVE (resumen §47)

Net PnL>0 · PF≥1.30 · Sharpe≥1.20 · Sortino≥1.50 · MaxDD≤8% · Expectancy>0 · ≥200 trades + superar determinista, ML y comparar Buy&Hold, todo NETO.

## Checklist analítico

1. Métricas calculadas sobre Net/Fully Loaded PnL.
2. Número de muestras declarado (trades, no días).
3. ICs con método explícito (percentile bootstrap, B≥1000, seed registrado).
4. Rechazo automático de estrategias que solo funcionan en un punto del espacio de parámetros.
5. Conclusión honesta: "no aporta valor" ES un resultado válido (PRD §2).

## Errores comunes

- Reportar Sharpe puntual sin IC.
- Monte Carlo que reordena trades violando dependencia temporal sin justificarlo.
- Múltiples comparaciones sin corrección → falsos descubrimientos.

## Referencias

- PRD §45–48. Skills: walk-forward-validacion, backtesting, release-readiness.
