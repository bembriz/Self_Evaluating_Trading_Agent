---
name: data-leakage
description: Usar al implementar features, backtests, recuperación de memoria/RAG o pipelines ML — siempre que exista riesgo de usar información futura (lookahead) en decisiones en t (PRD §34)
---

# data-leakage — Restricción crítica: cero información futura

## Propósito

Garantizar que una decisión generada en T solo use conocimiento disponible antes de T. Es restricción transversal: features, backtest, ML y RAG.

## Cuándo usar

- Calcular indicadores/features (ventanas, shift, rolling).
- Recuperar memoria vectorial (`memory.outcome_timestamp < decision_timestamp`).
- Entrenar ML / walk-forward (train estrictamente anterior a validation/forward).
- Diseñar tests anti-lookahead de cualquier fase.

**Cuándo NO:** nunca está "de más" aquí; si hay duda, aplica esta skill.

## Reglas duras

1. Features en t usan datos cerrados hasta t-1 inclusive; vela actual solo si CONFIRMADA.
2. Memoria: solo trades CERRADOS con outcome previo al timestamp de decisión; reflexiones entran tras cierre del trade.
3. Normalizadores/estadísticos (media, scaler) fit solo con pasado.
4. Holdout jamás participa en fit, prompts ni selección.
5. Tests automáticos que lo comprueban en cada fase aplicable.

## Checklist — patrón de test anti-lookahead

- Corruptor temporal: inyecta valores absurdos en el futuro del dataset ⇒ verifica que la salida en t NO cambia.
- Orden estricto: para cada memoria recuperada, assert `outcome_ts < decision_ts`.
- Replay determinista: correr pipeline hasta t, luego hasta t+k con datos truncados a t debe dar idéntico estado en t.

```python
def test_no_uses_future_candles(feature_engine, candles):
    base = feature_engine.compute(candles[:100])
    envenenadas = candles.copy(); envenenadas.loc[100:, "close"] = 10**9
    assert feature_engine.compute(envenenadas)[:100] == base
```

## Errores comunes

- `rolling().mean()` sin shift incluida la vela corriente.
- RAG sin filtro temporal "porque los embeddings ya filtran" (falso).
- Scaler fit sobre todo el histórico antes de walk-forward.

## Referencias

- PRD §34, §30, §42–44. Skills: backtesting, rag-memoria, walk-forward-validacion, testing-unit.
