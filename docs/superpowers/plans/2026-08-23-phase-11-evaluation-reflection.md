# Fase 11 — Evaluation & Reflection: Plan de Implementación

> Ejecución en línea. Dominio puro para evaluación/proposals; servicios de aplicación para flujos.

**Goal:** Evaluar trades cerrados (MFE/MAE), generar reflexiones estructuradas (PRD §35),
insertarlas en memoria solo con outcome cerrado, y proponer mejoras sin auto-aplicarlas
con workflow de aprobación humana (PRD §36).

## Tasks

### Task A: Outcome evaluator + MFE/MAE
- Create: `src/domain/evaluation/outcome.py` (`TradeOutcome`, `evaluate_outcome`)
- Test: `tests/test_outcome_evaluator.py`
- MFE = max(highest) − entry ≥ 0; MAE = max(0, entry − min(lowest)); result WIN/LOSS/BREAKEVEN por net_pnl.

### Task B: Reflection Engine determinista
- Create: `src/application/services/reflection_engine.py`
- Test: `tests/test_reflection_engine.py`
- Reglas puras: pérdida con MAE grande→COUNTER_TREND_ENTRY; win con MFE≫capturado→PREMATURE_EXIT; breakeven→NO_EDGE; genérico→EXECUTION_OK. Nunca modifica estrategia/riesgo (PRD §35).

### Task C: Inserción en memoria solo trade cerrado
- Create: `src/application/services/memory_writer.py`
- Test: `tests/test_memory_writer.py`
- Usa EmbeddingProvider+MemoryRepository (fakes); rechaza reflexiones de trades no cerrados.

### Task D: Improvement proposals + aprobación humana
- Create: `src/domain/experiments/improvement.py`, `src/application/services/approval_workflow.py`
- Test: `tests/test_improvement_proposals.py`
- Proposal inmutable con estado; approve solo humano (PermissionError si no); jamás auto-aplica cambios a estrategia/riesgo (PRD §36).
