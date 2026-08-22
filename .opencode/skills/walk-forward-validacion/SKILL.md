---
name: walk-forward-validacion
description: Usar al diseñar o ejecutar validación walk-forward, separaciones temporales train/validation/holdout, congelar el holdout, o evaluar degradación out-of-sample (PRD §42-44)
---

# walk-forward-validacion — Ventanas sucesivas sin shuffle

## Propósito

Evaluar estrategias/modelos como lo hará la realidad: entrenar con pasado, validar en ventana siguiente, avanzar. Nunca shuffle temporal. Holdout intocable hasta estrategia FROZEN.

## Cuándo usar

- Fase 07 (ML baseline) y 14 (walk-forward completo).
- Antes de promover cualquier parámetro/prompt/estrategia.
- Al definir/congelar la separación temporal del dataset.

**Cuándo NO:** backtests puntuales de una sola ventana (backtesting); análisis estadístico post-hoc (validacion-estadistica).

## Esquema estándar

```text
Dataset ≥36m (BYBIT_ETHBTC_V###) — separación congelada ANTES de optimizar:
  Development/WalkForward ≈ primeros ~30 meses
  Final Holdout           = últimos ~6 meses (BLOQUEADO)

WF: [Train][Val] → desplaza → [Train'][Val'] → ... sin solapamientos futuros
```

## Reglas duras

1. La separación exacta se congela y versiona ANTES de la primera optimización.
2. Holdout: ni fit, ni prompts, ni selección de modelos, ni RAG; solo se abre con estrategia FROZEN y una sola vez.
3. Sin shuffle: el orden temporal es sagrado.
4. Reportar SIEMPRE degradación train→validation→holdout.
5. Cada ventana registra experiment_id completo (PRD §39).

## Checklist por corrida WF

1. Manifest del dataset + hash verificado.
2. Ventanas definidas paramétricamente (tamaño/paso) y persistidas.
3. Por ventana: métricas in-sample vs out-of-sample.
4. Agregado: estabilidad entre ventanas (dispersión, signo consistente).
5. Detección de overfitting: caída brusca OOS = señal roja para gate §47.
6. Evidencia + tabla comparativa en reporte de fase.

## Errores comunes

- "Walk-forward" con ventanas que solapan futuro en validation.
- Tocar el holdout "solo para ver".
- Optimizar por mejor ventana individual en lugar de estabilidad global.

## Referencias

- PRD §42–44, §47. Skills: data-leakage, validacion-estadistica, backtesting.
