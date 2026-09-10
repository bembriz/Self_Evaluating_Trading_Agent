# Paper Certification Gate (16c.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar formalmente la certificación **Paper** (integridad operacional) de la validación estadística (Replay) y sustituir el gate actual (`MIN_TRADES=200`, regímenes) por un evaluador determinista de criterios operacionales independientes.

**Architecture:** Reescribir `harness/scripts/paper_certification.py` como evaluador puro y determinista: normaliza un `state` (JSON) a un `CertificationReport` estructurado (`overall_status`, `evaluated_at`, `certification_age_days`, `checks[]`, `failure_reasons[]`). Un fallo obligatorio ⇒ `FAIL` sin promedio ni compensación. No toca `src/`.

**Tech Stack:** Python 3.12, stdlib (json/dataclasses/argparse/datetime), pytest, ruff. Sin dependencias nuevas.

## Global Constraints

- No modificar `src/` (PaperRunner, PaperEngine, RiskEngine, Portfolio, EmaRsiBaseline, fees, slippage, execution, recovery, decision_context). Si un test revela un defecto real en producción: **detenerse y reportar**, no corregir en este trabajo.
- Ventana de certificación = **30 días** (`>= 30.0` días reales en UTC). `29d 23h 59m 59s` ⇒ FAIL.
- `MIN_TRADES=200` eliminado como requisito. `trade_count` es alias legacy de `fill_count`; nunca criterio de certificación.
- `coverage >= 80%` para el arnés (`harness/tests`, source `scripts`).
- `ruff` line-length 100, target py312, select `E,F,I,UP,B,SIM`.
- Sin commit/push/merge/tag/release sin GATE (bloqueados por enforcement).

---

### Task 1: Esquema de estado v2 + normalización de timestamps

**Files:**
- Modify: `harness/scripts/paper_certification.py`

**Interfaces:**
- Consumes: nada.
- Produces: `CERTIFICATION_WINDOW_DAYS = 30`, `FROZEN_VERSION_KEYS` (tuple de 10), `_to_epoch_seconds(value) -> float | None`, `_as_pass(value) -> bool`, `_as_number(value) -> float | None`.

**Estado v2 canónico (JSON):**

```json
{
  "schema_version": 2,
  "session_id": "paper-0.2.0-20260901",
  "session_started_at": "2026-09-01T00:00:00Z",
  "frozen": {
    "git_commit": "<sha>", "application_version": "0.2.0",
    "strategy_version": "baseline-v1", "risk_config_version": "risk-v1",
    "docker_image_digest": "sha256:...", "symbol": "ETHUSDT",
    "timeframe": "15m", "initial_capital": "1000.00",
    "fees_slippage_config_version": "fees-v1",
    "certification_started_at": "2026-09-01T00:00:00Z"
  },
  "current": { "…los mismos 10 campos, valores observados ahora…" },
  "operational": {
    "accounting_residual": 0.0, "recovery_integrity": "PASS",
    "unexplained_market_gaps": 0, "market_evidence_complete": "PASS",
    "decision_context_coverage": 100.0, "state_continuity": "PASS",
    "metrics_history_days": 30.0, "critical_errors": [],
    "certification_reports_complete": "PASS", "kill_switch_tested": "PASS",
    "daily_loss_tested": "PASS", "fill_count": 0,
    "closed_trade_count": 0, "trade_count": 0
  },
  "status": null, "invalidated_reason": null
}
```

**Reglas de lectura robusta:** todo se lee con `.get()` + default; la ausencia de un campo produce un check `FAIL` con evidencia `missing`, nunca un crash. El estado legacy (plano: `strategy_version`, `strategy_hash`, `active_strategy_hash`, `calendar_days`, `trade_count`, `market_regimes`, `periodic_reports`) se lee sin error: `trade_count`/`market_regimes`/`calendar_days` legacy **no** alimentan ningún criterio (solo `status` y, opcionalmente, la detección de drift de hash legacy → FAIL).

- [ ] **Step 1:** escribir test `test_legacy_state_reads_without_error` + `test_missing_fields_produce_fail_not_crash`
- [ ] **Step 2:** verificar RED (funciones no existen)
- [ ] **Step 3:** implementar helpers de parseo/normalización
- [ ] **Step 4:** verificar GREEN
- [ ] **Step 5:** commit (autorizado tras GATE global; aquí solo staging)

### Task 2: Edad de certificación real en UTC

**Files:** `harness/scripts/paper_certification.py`

**Interfaces:**
- Produce: `_certification_age_days(frozen: Mapping, evaluated_at: str | None) -> float | None` (None si falta `certification_started_at`).

**Reglas:**
- `age = (evaluated_at_epoch_s - frozen.certification_started_at_epoch_s) / 86_400`.
- `evaluated_at` es parámetro explícito (ISO UTC o epoch ms); default `now`.
- `29d23h59m59s` ⇒ `age ≈ 29.999988 < 30` ⇒ FAIL. `>= 30.0` ⇒ PASS.
- `session_started_at` es informativo; `certification_started_at` ancla el reloj; jamás se re-ancla desde `current`.

- [ ] **Step 1:** tests `test_29_days_fails`, `test_30_days_pass`, `test_29d23h59m59s_fails`
- [ ] **Step 2:** RED
- [ ] **Step 3:** implementar
- [ ] **Step 4:** GREEN

### Task 3: Verificación de versiones congeladas (drift)

**Files:** `harness/scripts/paper_certification.py`

**Interfaces:**
- Produce: `_frozen_version_drift(frozen, current) -> list[str]` (keys que difieren).

**Reglas:** comparar los 10 `FROZEN_VERSION_KEYS` entre `frozen` y `current` con normalización int↔float. Cualquier diferencia ⇒ `frozen_versions` FAIL (overall FAIL). No re-anclar reloj.

- [ ] **Step 1:** test `test_version_drift_fails` (drift de `strategy_version` con 30 días y todo lo demás OK)
- [ ] **Step 2:** RED / **Step 3:** implementar / **Step 4:** GREEN

### Task 4: Los 13 checks operacionales + resultado estructurado

**Files:** `harness/scripts/paper_certification.py`

**Interfaces:**
- Produce:
  - `@dataclass(frozen=True, slots=True) CertificationCheck: name, status, observed, required, evidence`
  - `@dataclass(frozen=True, slots=True) CertificationReport: overall_status, evaluated_at, certification_age_days, checks, failure_reasons` + `to_dict()` + `to_markdown()`
  - `evaluate_certification(state: Mapping[str, Any], *, evaluated_at: str | None = None) -> CertificationReport`

**Criterios (nombre → regla):**

| check | regla |
|---|---|
| calendar_days | age `>= 30.0` |
| frozen_versions | `_frozen_version_drift(...) == []` |
| accounting_residual | `== 0` (exacto) |
| recovery_integrity | `_as_pass` |
| unexplained_market_gaps | `== 0` |
| market_evidence_complete | `_as_pass` |
| decision_context_coverage | `>= 100.0` |
| state_continuity | `_as_pass` |
| metrics_history_days | `>= 30.0` |
| critical_errors | vacío o todos `explained` |
| certification_reports_complete | `_as_pass` |
| kill_switch_tested | `_as_pass` |
| daily_loss_tested | `_as_pass` |

**Semántica de estado:**
- `state["status"] == "INVALIDATED"` ⇒ `overall_status = INVALIDATED` (razón preservada).
- Cualquier check FAIL ⇒ `overall_status = FAIL` (`failure_reasons` con un ítem por check fallido).
- Todos PASS ⇒ `overall_status = PASS`.
- `fill_count`/`closed_trade_count`/`trade_count` jamás gate.

**critical_errors:** lista de objetos `{"message": str, "explained": bool, "classification": str?}`. PASS si `len==0` o `all(explained)`.

- [ ] **Step 1:** tests de casos obligatorios (ver Task 5)
- [ ] **Step 2:** RED / **Step 3:** implementar / **Step 4:** GREEN

### Task 5: Casos TDD obligatorios

**Files:** `harness/tests/test_paper_certification.py` (reescribir gate tests; conservar `invalidate_state`/`reset_certification_state`/CLI tests adaptados)

1. 29 días + todo correcto ⇒ FAIL
2. 30 días + 0 fills + todo operacional correcto ⇒ PASS
3. 30 días + 1 fill ⇒ puede PASS
4. 30 días + 500 fills ⇒ no concede PASS por sí mismo (un fallo operacional ⇒ FAIL)
5. 30 días + `accounting_residual != 0` ⇒ FAIL
6. 30 días + `unexplained_market_gaps > 0` ⇒ FAIL
7. 30 días + `decision_context_coverage < 100` ⇒ FAIL
8. 30 días + `metrics_history_days < 30` ⇒ FAIL
9. 30 días + version drift ⇒ FAIL
10. 30 días + `recovery_integrity=FAIL` ⇒ FAIL
11. `critical_errors` con uno no explicado ⇒ FAIL
12. `critical_errors` con uno explicado/clasificado ⇒ PASS (comportamiento definido y testeado)
13. legacy `certification-state` ⇒ lectura compatible (sin excepción)
14. ausencia de `MIN_TRADES`/`trade_count` ⇒ no bloquea

### Task 6: CLI estructurado

**Files:** `harness/scripts/paper_certification.py`

**Interfaces:**
- `main(argv)` conserva `--state --report --invalidate --reason --archive`; añade `--evaluated-at` (ISO) y `--json-report PATH` (resultado machine-readable).
- Modo `--invalidate`: conserva `invalidate_state` (archivo INVALIDATED) + `reset_certification_state` (estado limpio legacy; el runner 0.1.x sigue escribiendo plano). No reescribe evidencia previa.
- Salida stdout: `overall_status`.

### Task 7: Quality gates + commit-candidate

- `uv run pytest harness/tests --cov=harness/scripts --cov-branch --cov-fail-under=80`
- `uv run pytest --cov=src --cov-branch --cov-fail-under=90` (suite completa producto, sin cambios en src)
- `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy src tests`
- Secret scan (gitleaks/trufflehog o equivalente disponible)
- codebase-memory: re-index, `detect_changes`, `check_index_coverage`, blast radius.
- Redactar `docs/phases/16c/commit-candidate-006.md` y esperar GATE.

## Self-Review

- **Spec coverage:** separación Replay/Paper ✓ (Task 4), 13 criterios ✓, 30d UTC real ✓ (Task 2), trade/fill semantics ✓ (Task 4 + docstring), 14 casos TDD ✓ (Task 5), freeze de 10 campos ✓ (Task 3), resultado estructurado ✓ (Task 4), estado histórico INVALIDATED ✓ (Task 6), no-tocar-src ✓ (constraint global).
- **Placeholder scan:** sin TBD/TODO.
- **Type consistency:** `CertificationReport`, `CertificationCheck`, `evaluate_certification`, `_certification_age_days`, `_frozen_version_drift` referenciados de forma consistente.
