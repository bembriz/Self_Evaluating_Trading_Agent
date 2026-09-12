# FASE 17F — Walk-Forward + Robustness (resultado: edge negativo estable)

> Solo lab + runtimes existentes. Sin BacktestEngine promocional, sin
> auto-optimización, sin selección de variantes, sin holdout, sin EDGE_PRESENT.

- Base: `c8f34e1`. Motor: EmaRsiBaseline + PaperEngine reales, timing MVP-A,
  `risk-v1-nostop-mvp-a` (documentado en `walkforward.json`/`robustness.json`:
  con atr=None el BUY exige stop desactivado para ser ejercitable; el engine
  no se modificó).
- Métricas reutilizadas de `domain.evaluation.metrics` (`compute_metrics`):
  round-trips reconstruidos de la traza, curva de equity de traza + inicial.

## Walk-forward (WALK_FORWARD [62208,88128), 3×8640 filas)

| Ventana | Rango | Trades | Net PnL | Return | PF |
|---|---|---|---|---|---|
| 0 | [62208,70848) | 77 | -3.08 | -0.31% | 0.49 |
| 1 | [70848,79488) | 95 | -7.02 | -0.70% | 0.13 |
| 2 | [79488,88128) | 81 | -5.97 | -0.60% | 0.24 |

Agregado: net **-16.07** (-1.61%), mediana -0.60%, peor -0.70%, max DD 0.63%,
253 trades, PF 0.0, expectancy -0.064. 0/3 ventanas rentables.
Double-run representativo (ventana 0): hashes idénticos.

## Robustness (DEVELOPMENT completo, 7 variantes 1-a-1)

Todas las variantes en [-20.09, -20.02] (406–449 trades): STABLE=YES —
edge negativo consistente, no depende de un punto hiperespecífico.
Distribución reportada, ninguna variante seleccionada ni promovida.

## Calidad (evidencia en este directorio)

| Check | Resultado |
|---|---|
| tests/lab (225) | 225 passed |
| tests/integration | 15 passed |
| global `--cov=src --cov-branch --cov-fail-under=90` | 665 passed · **95.67%** ✔ |
| `walk_forward.py` + `robustness.py` | 100% statements, 100% branches ✔ |
| `ruff check` / `format --check` / `mypy src tests` (220) | PASS / PASS / PASS |

## Safety

HOLDOUT PRISTINE (solo bloqueos testeados, cero lecturas); runtime
protegido CLEAN. Cada ventana/variante con su SpecId; cambio de
parámetros ⇒ SpecId distinto (testeado).
