# ADR-0004 — Baseline ML en Python puro (Logistic Regression sin scikit-learn)

**Fecha:** 2026-08-23
**Estado:** accepted

## Contexto

La Fase 07 exige un baseline ML reproducible (Logistic Regression, PRD §30) con pipeline sin fuga, walk-forward y experiment tracking (§39). El proyecto opera bajo control estricto de dependencias (PRD §11, skill `infra-control`): toda instalación requiere Dependency Proposal + USER GATE. El PRD §15 ya sentó el precedente de "implementar internamente cuando sea razonable" (aplicado a indicadores en ADR-0002).

## Decisión

1. **Regresión logística binaria en stdlib puro** (`domain/experiments/logistic_regression.py`): gradient descent batch con pesos inicializados a cero (determinista, sin aleatoriedad), sigmoid con clip `[-30, 30]` para estabilidad numérica y regularización L2 opcional. Sin numpy ni scikit-learn.
2. **Pipeline reproducible y causal**: `build_features` (features en `t` solo usan datos ≤ `t`), `WalkForwardSplitter` (cronológico, train `<` validation, holdout excluido), entrenamiento por ventana, señales → `BacktestEngine` reusado de Fase 06 para métricas comparables.
3. **Experiment tracking inmutable**: `experiment_id` = SHA-256 de la serialización canónica de parámetros (sin timestamps); cambiar un parámetro cambia el id.

## Alternativas consideradas

| Opción | Consecuencia si se elige |
|---|---|
| scikit-learn + numpy | Dependency Proposal + USER GATE obligatorio; superficie de dependencias mucho mayor; desproporcionado para un baseline logístico de pocas features |
| numpy a secas | Misma fricción de DP/gate; beneficio marginal frente a stdlib |

## Consecuencias

### Positivas

- Cero dependencias nuevas: sin Dependency Proposal ni gate adicional.
- Determinismo total (pesos a cero, gradient descent determinista) verificable con test de dos corridas idénticas.
- El baseline logístico es sencillo y testeable (100% branch); el objetivo es ser referencia, no sofisticación (PRD §29).

### Negativas / trade-offs aceptados

- Gradient descent propio es más lento que sklearn (irrelevante para ~10⁴ muestras × pocas features).
- Sin métricas avanzadas de sklearn (ROC-AUC, CV); se implementan accuracy/precision/recall, suficientes para un baseline.
- L2 con learning_rate alto puede oscilar (documentado; defaults estables).

### Neutras

- Si una fase posterior requiere ML no-lineal o análisis estadístico pesado, se podrá justificar numpy/scikit-learn mediante Dependency Proposal.
