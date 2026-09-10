# Paper Certification State v2 Producer (16c.6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar el producto real (paper-runner) con el gate de certificación v2: un productor en `src/` que emite `certification-state` schema v2 (`frozen`/`current`/`operational`) a partir de estado real persistido, reconciliación contable Decimal, evidencia de safeguards ligada al artefacto, y un E2E productor→JSON→evaluador PASS — habilitando el bump `0.2.0` y el cierre integrado de 16c.

**Architecture:** El evaluador ya existe y es inmutable (`harness/scripts/paper_certification.py`, schema v2, 13 checks, `FROZEN_VERSION_KEYS` 10 campos). Esta fase añade el **productor** en `src/application/services/certification_snapshot.py`: dado `previous` estado, `events` (DB), velas persistidas, artefacto runtime y `now_ms`, produce el dict v2 canónico. `frozen` es inmutable (ancla una vez); `current` se refresca; `operational` se deriva por kernels puros y por una reconciliación contable espejo del engine (`accounting_reconciliation.py`). `_run_loop` (CLI) invoca el productor en cada escritura periódica y conserva las claves legacy planas para compatibilidad de lectura. Los safeguards (`kill_switch_tested`/`daily_loss_tested`) se emiten PASS solo con evidencia previa compatible con el artefacto congelado, generada por un drill operativo previo a la certificación (`harness/scripts/safeguard_drill.py`, secuencias completas, fuera del producto) — **sin** caminos especiales en PaperRunner/RiskEngine/Portfolio.

**Tech Stack:** Python 3.12, stdlib + SQLAlchemy/pgvector existentes, pytest, ruff (line-length 100, py312, `E,F,I,UP,B,SIM`), mypy. Sin dependencias nuevas. Decimal del stdlib para la reconciliación.

## Global Constraints

- No modificar la matemática de trading ni el cálculo de ejecución existente (fees/slippage/exec). La reconciliación **replica** la aritmética del engine (mismo orden de operaciones float) para que `residual == 0` sea bit-exacto sobre los mismos operandos persistidos.
- `exec_price` ya embebe slippage ⇒ **nunca** deducir `slippage_cost` dos veces. `fee` se deduce una sola vez.
- `accounting_residual == 0` es obligatorio; nunca emitir 0 artificial.
- `certification_started_at` = ancla persistente e inmutable de la NUEVA certificación 0.2.0 (nunca se re-ancla desde `current`; ausencia/drift ⇒ FAIL sin re-anclar).
- `metrics_history_days` = **evidencia real de cobertura de métricas** (heartbeats diarios confirmados), no tiempo transcurrido.
- `kill_switch_tested`/`daily_loss_tested` = PASS solo si existe evidencia de drill compatible con `{git_commit, application_version, docker_image_digest, strategy_version, risk_config_version}` del `frozen`. Sin `--drill` en paper-runner.
- El E2E usa el MISMO productor que el paper-runner desplegado; no construye JSON v2 a mano.
- No tocar el evaluador (`harness/scripts/paper_certification.py` es entregable cerrado de 16c.4).
- El LLM del producto no toca el Risk Engine ni habilita LIVE (regla de producto, respetada: el productor solo LEE evidencia).
- Gates: cobertura `src >= 90%` (`--cov-fail-under=90`), arnés `harness >= 80%`; ruff/mypy limpios; sin secrets; sin data leakage (todo deriva de eventos/velas con `timestamp_ms <= now_ms`).
- Sin commit/push/merge/tag/release sin GATE (enforcement). Los cambios de esta fase viven en `fix/phase-16c-restart-safe` (worktree `/tmp/opencode/phase-16c-restart-safe`).

---

### Task 1: Metadatos de artefacto runtime + Settings

**Files:**
- Modify: `src/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `Settings.git_commit: str = ""` (env `GIT_COMMIT`), `Settings.docker_image_digest: str = ""` (env `DOCKER_IMAGE_DIGEST`), `Settings.paper_safeguard_evidence_path: str = "docs/phases/16/safeguard-evidence.json"` (env `PAPER_SAFEGUARD_EVIDENCE_PATH`).

- [ ] **Step 1: Write the failing test**

`tests/test_settings.py` (append):

```python
def test_certification_artifact_settings_defaults():
    s = Settings()  # type: ignore[call-arg]  # fixture carga .env
    assert s.git_commit == ""
    assert s.docker_image_digest == ""
    assert s.paper_safeguard_evidence_path == "docs/phases/16/safeguard-evidence.json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py::test_certification_artifact_settings_defaults -q`
Expected: FAIL (`AttributeError`/missing fields).

- [ ] **Step 3: Implement**

En `src/settings.py`, en la clase `Settings` (junto a `paper_certification_state_path`), añadir:

```python
    git_commit: str = ""
    docker_image_digest: str = ""
    paper_safeguard_evidence_path: str = "docs/phases/16/safeguard-evidence.json"
```

Y en el bloque de mapeo env (donde el resto de campos lee `os.getenv`), mapear `GIT_COMMIT`, `DOCKER_IMAGE_DIGEST`, `PAPER_SAFEGUARD_EVIDENCE_PATH`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -q`
Expected: PASS.

- [ ] **Step 5: Commit** (tras GATE global; aquí solo `git add`).

---

### Task 2: Núcleo del productor — frozen/current + ancla del reloj

**Files:**
- Create: `src/application/services/certification_snapshot.py`
- Test: `tests/test_certification_snapshot.py`

**Interfaces:**
- Consumes: `PaperRunSummary` (`src/application/services/paper_runner.py:91-113`), `RiskConfig` (`src/domain/risk/config.py`), `FeeModel`/`SlippageModel` (defaults de instancia; NO acceso a `.version` como class-var de un dataclass slots), `Settings`.
- Produces:
  - `FEES_SLIPPAGE_CONFIG_VERSION = f"{FeeModel().version}+{SlippageModel().version}"`
  - `@dataclass(frozen=True, slots=True) RuntimeArtifact: git_commit, application_version, docker_image_digest, strategy_version, strategy_hash, risk_config_version, fees_slippage_config_version, symbol, timeframe, initial_capital: float, certification_started_at_ms: int | None`
  - `runtime_artifact(*, summary: PaperRunSummary, app_version: str, git_commit: str, docker_image_digest: str, risk_config: RiskConfig, now_ms: int) -> RuntimeArtifact` (`certification_started_at_ms = now_ms`, ancla candidata)
  - `_iso_utc_ms(ms: int) -> str` (ISO-8601 con sufijo `Z`)
  - `_block(artifact: RuntimeArtifact) -> dict[str, object]` — las 9 claves observadas del artefacto (sin `certification_started_at`)
  - `_frozen_block(artifact: RuntimeArtifact, started_at_ms: int) -> dict[str, object]` — 10 claves de `FROZEN_VERSION_KEYS`, con `certification_started_at` ISO
  - `_current_block(artifact: RuntimeArtifact, *, started_at_iso: str) -> dict[str, object]` — **10 claves**: las 9 observadas + `certification_started_at = started_at_iso`. `current` refleja el ancla EN VIGOR (la de `frozen`); si un proceso re-anclara el reloj silenciosamente, `current.certification_started_at != frozen.certification_started_at` ⇒ el evaluador detecta drift.
  - `_resolve_frozen(previous: Mapping[str, Any], artifact: RuntimeArtifact) -> dict[str, object]` — inmutable y puro: si `previous.frozen` existe y es compatible (mismo `symbol`, `timeframe`, `application_version`, `strategy_version`) lo conserva intacto; si no (ausente, legacy plano, o artefacto distinto) **ancla nuevo** con `certification_started_at = _iso_utc_ms(artifact.certification_started_at_ms)`; `ValueError` si el ancla es `None`.
  - `session_started_at_ms(summary, now_ms) -> int` (= `summary.first_timestamp_ms` si existe, si no `now_ms`).

**Regla de ancla (decisión 16c.6):** en la primera escritura v2 de la sesión 0.2.0 el productor ancla `certification_started_at = now_ms` de esa escritura (inicio real del deploy). Si el `previous` es legacy plano (runner 0.1.x) o no tiene `frozen` compatible, se trata como sesión nueva y se ancla; jamás se hereda un reloj viejo. Las escrituras siguientes conservan `previous["frozen"]` intacto y componen `current` con el `certification_started_at` de ese `frozen`.

**Calidad obligatoria en cada paso de código:** `ruff format` aplicado (`uv run ruff format src/application/services/certification_snapshot.py tests/test_certification_snapshot.py`), `uv run ruff check` limpio en ambos, y `uv run mypy src/application/services/certification_snapshot.py` con 0 errores (strict). El módulo debe quedar mypy-strict-clean (sin `src.` prefix; `PaperRunSummary` solo bajo `TYPE_CHECKING`).

- [ ] **Step 1: Write the failing test**

`tests/test_certification_snapshot.py` (create):

```python
from application.services.certification_snapshot import (
    _current_block, _iso_utc_ms, _resolve_frozen, runtime_artifact,
)
from application.services.paper_runner import PaperRunSummary
from domain.risk.config import RiskConfig

FROZEN_KEYS = {
    "git_commit", "application_version", "strategy_version", "risk_config_version",
    "docker_image_digest", "symbol", "timeframe", "initial_capital",
    "fees_slippage_config_version", "certification_started_at",
}

def _summary() -> PaperRunSummary:
    return PaperRunSummary(
        session_id="paper-baseline-ETHUSDT-15m", decision_source="baseline",
        strategy_version="baseline-v1", strategy_hash="h" * 64,
        symbol="ETHUSDT", timeframe="15m",
        first_timestamp_ms=1_700_000_000_000, latest_timestamp_ms=1_700_000_300_000,
        decisions={"BUY": 0, "SELL": 0, "HOLD": 1}, fills=0, fees=0.0, slippage=0.0,
        latest_equity=1000.0, kill_switch_active=False, initial_equity=1000.0,
    )

def _artifact(now_ms: int):
    return runtime_artifact(
        summary=_summary(), app_version="0.2.0", git_commit="abc1234",
        docker_image_digest="sha256:deadbeef", risk_config=RiskConfig(), now_ms=now_ms,
    )

def test_iso_utc_ms_suffix_z():
    assert _iso_utc_ms(1_700_000_000_000).endswith("Z")

def test_frozen_and_current_carry_the_10_frozen_keys():
    artifact = _artifact(1_700_000_000_000)
    started = _iso_utc_ms(1_700_000_000_000)
    frozen = _resolve_frozen({"schema_version": 1, "trade_count": 0}, artifact)
    current = _current_block(artifact, started_at_iso=frozen["certification_started_at"])
    assert set(frozen) == FROZEN_KEYS
    assert set(current) == FROZEN_KEYS
    assert current["certification_started_at"] == frozen["certification_started_at"]

def test_resolve_frozen_legacy_prev_anchors_fresh():
    now_ms = 1_700_000_000_000
    frozen = _resolve_frozen({"schema_version": 1, "trade_count": 0}, _artifact(now_ms))
    assert frozen["certification_started_at"] == _iso_utc_ms(now_ms)

def test_resolve_frozen_keeps_previous_frozen_when_compatible():
    previous = {
        "schema_version": 2, "session_id": "paper-baseline-ETHUSDT-15m",
        "frozen": {"symbol": "ETHUSDT", "timeframe": "15m", "application_version": "0.2.0",
                   "strategy_version": "baseline-v1",
                   "certification_started_at": "2026-09-01T00:00:00Z"},
    }
    frozen = _resolve_frozen(previous, _artifact(1_700_000_300_000))
    assert frozen["certification_started_at"] == "2026-09-01T00:00:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_certification_snapshot.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
"""Productor del certification-state schema v2 (16c.6).

Convierte estado real persistido (resumen, eventos, velas) + artefacto runtime en
el JSON v2 que consume harness/scripts/paper_certification.py. frozen es
inmutable (ancla de certificación); current se refresca en cada escritura y
lleva las mismas 10 claves que frozen (el evaluador compara frozen vs current
clave a clave para detectar drift de versiones / re-ancla del reloj).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from domain.risk.config import RiskConfig
from domain.trading.fees import FeeModel
from domain.trading.slippage import SlippageModel

if TYPE_CHECKING:  # evita ciclo de import con paper_runner (Task 5)
    from application.services.paper_runner import PaperRunSummary

FEES_SLIPPAGE_CONFIG_VERSION = f"{FeeModel().version}+{SlippageModel().version}"


def _iso_utc_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def session_started_at_ms(summary: PaperRunSummary, now_ms: int) -> int:
    return summary.first_timestamp_ms if summary.first_timestamp_ms is not None else now_ms


@dataclass(frozen=True, slots=True)
class RuntimeArtifact:
    git_commit: str
    application_version: str
    docker_image_digest: str
    strategy_version: str
    strategy_hash: str
    risk_config_version: str
    fees_slippage_config_version: str
    symbol: str
    timeframe: str
    initial_capital: float
    certification_started_at_ms: int | None


def runtime_artifact(
    *,
    summary: PaperRunSummary,
    app_version: str,
    git_commit: str,
    docker_image_digest: str,
    risk_config: RiskConfig,
    now_ms: int,
) -> RuntimeArtifact:
    return RuntimeArtifact(
        git_commit=git_commit,
        application_version=app_version,
        docker_image_digest=docker_image_digest,
        strategy_version=summary.strategy_version,
        strategy_hash=summary.strategy_hash,
        risk_config_version=risk_config.version,
        fees_slippage_config_version=FEES_SLIPPAGE_CONFIG_VERSION,
        symbol=summary.symbol,
        timeframe=summary.timeframe,
        initial_capital=risk_config.capital,
        certification_started_at_ms=now_ms,  # ancla candidata = tiempo de esta escritura
    )


def _block(artifact: RuntimeArtifact) -> dict[str, object]:
    return {
        "git_commit": artifact.git_commit,
        "application_version": artifact.application_version,
        "strategy_version": artifact.strategy_version,
        "risk_config_version": artifact.risk_config_version,
        "docker_image_digest": artifact.docker_image_digest,
        "symbol": artifact.symbol,
        "timeframe": artifact.timeframe,
        "initial_capital": artifact.initial_capital,
        "fees_slippage_config_version": artifact.fees_slippage_config_version,
    }


def _frozen_block(artifact: RuntimeArtifact, started_at_ms: int) -> dict[str, object]:
    return {**_block(artifact), "certification_started_at": _iso_utc_ms(started_at_ms)}


def _current_block(artifact: RuntimeArtifact, *, started_at_iso: str) -> dict[str, object]:
    return {**_block(artifact), "certification_started_at": started_at_iso}


def _resolve_frozen(
    previous: Mapping[str, Any], artifact: RuntimeArtifact
) -> dict[str, object]:
    raw = previous.get("frozen")
    frozen: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    compatible = (
        str(frozen.get("symbol")) == artifact.symbol
        and str(frozen.get("timeframe")) == artifact.timeframe
        and str(frozen.get("application_version")) == artifact.application_version
        and str(frozen.get("strategy_version")) == artifact.strategy_version
    )
    if compatible:
        return dict(frozen)
    anchor_ms = artifact.certification_started_at_ms
    if anchor_ms is None:
        raise ValueError("certification anchor requires artifact.certification_started_at_ms")
    return _frozen_block(artifact, anchor_ms)
```

`_resolve_frozen` es puro: ancla con `artifact.certification_started_at_ms` (= `now_ms` de la escritura). En producción el productor (Task 5) construye el artefacto con el `now_ms` de cada escritura; la primera escritura (previous legacy/ausente) fija el ancla, las siguientes conservan `previous["frozen"]` y componen `current = _current_block(artifact, started_at_iso=frozen["certification_started_at"])`.

- [ ] **Step 4: Run tests + quality to verify pass**

Run:
`uv run pytest tests/test_certification_snapshot.py -q` → Expected: PASS (4 tests).
`uv run ruff format --check src/application/services/certification_snapshot.py tests/test_certification_snapshot.py && uv run ruff check src/application/services/certification_snapshot.py tests/test_certification_snapshot.py` → Expected: limpio.
`uv run mypy src/application/services/certification_snapshot.py` → Expected: 0 errores (strict).

- [ ] **Step 5: `git add`** (`tests/test_certification_snapshot.py`, `src/application/services/certification_snapshot.py`)

---

### Task 3: Kernels operacionales (decision_context, gaps, counts, heartbeats, state_continuity)

**Files:**
- Modify: `src/application/services/certification_snapshot.py`
- Test: `tests/test_certification_snapshot.py`

**Interfaces:**
- Produces:
  - `decision_context_coverage(events: Sequence[PaperTradeEvent]) -> float` (100.0 si `events` vacío; % de eventos con `decision_context` dict que contiene `schema_version` y `signal_reason`)
  - `fill_counts(events) -> tuple[int, int, int]` → `(fill_count, closed_trade_count, trade_count)`; `closed_trade_count` = fills `action=="SELL"` con `exit_reason` no vacío; `trade_count` = alias de `fill_count`
  - `slippage_and_fees(events) -> tuple[float, float]` (sumas de `slippage_cost` y `fee`)
  - `unexplained_gap_count(candles: Sequence[Candle], interval_ms: int) -> int` — buckets `interval_ms` faltantes entre el primer y último `timestamp_ms` de la lista (ordenada); devuelve 0 si < 2 velas o sin huecos
  - `market_evidence_complete(unexplained_gaps: int, candles: Sequence[Candle], events: Sequence[PaperTradeEvent]) -> str` — `"PASS"` si `unexplained_gaps == 0` y la primera/last vela acotan el rango de timestamps de los eventos; si no `"FAIL"`
  - `metrics_history_days(heartbeats: Sequence[str]) -> int` — n.º de fechas UTC distintas (`YYYY-MM-DD`)
  - `add_metrics_heartbeat(previous: Mapping[str, Any], today: str, artifact_ok: bool) -> list[str]` — añade `today` (dedup) solo si `artifact_ok`; conserva y devuelve la lista
  - `state_continuity(previous: Mapping[str, Any], *, application_version: str, session_id: str) -> str` — `"PASS"` si `previous` no tiene `schema_version==2` (primer ancla) o si `previous["schema_version"]==2` y `previous["application_version"]==application_version` y `previous["session_id"]==session_id`; si no `"FAIL"`
  - `recovery_integrity(critical_errors: Sequence[Mapping[str, Any]]) -> str` — `"PASS"` si no hay errores con `kind == "recovery_divergence"`; si no `"FAIL"`

**Reglas:** solo se usan datos con `timestamp_ms <= now_ms` (sin lookahead). `critical_errors` se persiste en el estado y lo alimenta el CLI (Task 4); `recovery_integrity` se deriva de él.

- [ ] **Step 1: Write failing tests** (una selección obligatoria)

```python
from application.services.certification_snapshot import (
    decision_context_coverage, fill_counts, metrics_history_days,
    state_continuity, unexplained_gap_count,
)
from application.ports.paper_trading import PaperTradeEvent
from domain.market.candle import Candle

def _ev(action, *, filled=True, ts=1_700_000_000_000, dc=None, exit_reason="", fee=0.0):
    return PaperTradeEvent(session_id="s", strategy_version="v", strategy_hash="h",
        decision_source="baseline", symbol="ETHUSDT", timeframe="15m", timestamp_ms=ts,
        action=action, filled=filled, risk_reason="", exit_reason=exit_reason,
        exec_price=100.0, quantity=1.0, fee=fee, slippage_cost=0.0, equity=1000.0,
        kill_switch_active=False, decision_context=dc)

def _candle(ts_ms: int) -> Candle:
    return Candle(timestamp_ms=ts_ms, open=100.0, high=101.0, low=99.0,
                  close=100.5, volume=1.0, turnover=100.5)

def test_coverage_100_when_all_contexts_present():
    dc = {"schema_version": 1, "signal_reason": "ema"}
    events = [_ev("BUY", dc=dc, ts=1), _ev("SELL", dc=dc, ts=2)]
    assert decision_context_coverage(events) == 100.0

def test_coverage_zero_when_context_missing():
    assert decision_context_coverage([_ev("BUY", dc=None)]) == 0.0

def test_fill_counts_closed_trade_requires_exit_reason():
    fill, closed, trade = fill_counts([_ev("SELL", ts=1), _ev("SELL", ts=2, exit_reason="tp")])
    assert (fill, closed, trade) == (2, 1, 2)

def test_gap_count_counts_missing_bucket():
    candles = [_candle(0), _candle(1_800_000)]  # falta el bucket 900_000
    assert unexplained_gap_count(candles, interval_ms=900_000) == 1

def test_state_continuity_fail_on_version_change():
    prev = {"schema_version": 2, "application_version": "0.1.3", "session_id": "s"}
    assert state_continuity(prev, application_version="0.2.0", session_id="s") == "FAIL"

def test_metrics_history_days_counts_distinct_dates():
    assert metrics_history_days(["2026-09-01", "2026-09-01", "2026-09-02"]) == 2
```

*(Nota: `Candle` = `domain.market.candle.Candle(timestamp_ms, open, high, low, close, volume, turnover)`; sin campos symbol/timeframe. Validación `high >= max(open, close)` y `low <= min(open, close)` en `__post_init__`.)*

- [ ] **Step 2: Run test to verify it fails** (`uv run pytest tests/test_certification_snapshot.py -q`)
- [ ] **Step 3: Implement** los helpers puros en `certification_snapshot.py`. `unexplained_gap_count` recorre la lista ordenada contando buckets faltantes: `expected = prev + interval_ms; if ts > expected: gaps += (ts - expected) // interval_ms`.
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: `git add`**

---

### Task 4: Reconciliación contable Decimal (espejo del engine)

**Files:**
- Create: `src/application/services/accounting_reconciliation.py`
- Test: `tests/test_accounting_reconciliation.py`

**Interfaces:**
- Consumes: `PaperTradeEvent` (flujos persistidos), velas persistidas `Candle`, `initial_capital: float`.
- Produces:
  - `@dataclass(frozen=True, slots=True) AccountingLedger: cash: Decimal, position_qty: Decimal, average_entry: Decimal, realized_pnl: Decimal, fees: Decimal, reconstructed_equity: Decimal`
  - `reconcile_accounting(events: Sequence[PaperTradeEvent], *, initial_capital: float, mark_price: float | None, interval_ms: int) -> AccountingLedger`
  - `residual(book_equity: float, ledger: AccountingLedger) -> Decimal` = `Decimal(str(book_equity)) - ledger.reconstructed_equity`
  - `latest_persisted_mark(candles: Sequence[Candle]) -> float | None` (close de la última vela, `None` si vacía)

**Reglas (decisiones 16c.6):**
- Los eventos persistidos son la verdad de ejecución. Se procesan en orden `timestamp_ms` ascendente.
- Se **replica** la aritmética del engine de papel (leer `src/application/services/paper_engine.py` `_handle_fill`/gestión de posición y `Portfolio` en `src/domain/portfolio/portfolio.py` para fijar el orden exacto de operaciones float y la semántica de posición abierta/cierre parcial) SIN modificar esa matemática. El objetivo es que, sobre los mismos operandos almacenados (los `str()` de las columnas float) y el mismo orden de operaciones, la recomputación sea bit-idéntica al `equity` persistido por el engine ⇒ `residual == 0` exacto.
- `exec_price` embebe slippage: el flujo de caja de un fill usa `exec_price` y **no** resta `slippage_cost` aparte. `fee` se deduce una sola vez por fill.
- Con posición abierta: `reconstructed_equity = cash + position_qty * mark_price`, donde `mark_price = latest_persisted_mark(...)` (evidencia de mercado persistida). Si hay posición abierta y `mark_price is None` ⇒ elevar `MissingMarkError` (el productor lo traduce a un check de fallo, no a crash).
- `residual` es `Decimal`; PASS solo con `residual == 0`.

**Casos obligatorios (test):**
1. flat exact reconciliation → residual 0
2. open position exact reconciliation → residual 0
3. multiple BUY/SELL fills → residual 0
4. fees included once → residual 0
5. slippage embedded in exec_price and NOT deducted twice → residual 0
6. deliberately altered fill (precio/qty) → residual != 0
7. altered fee → residual != 0
8. missing persisted event/fill → residual != 0
9. missing mark price with open position → `MissingMarkError`
10. corrupted accounting evidence → residual != 0 (producer/evaluator FAIL en Task 6)

- [ ] **Step 1: Read engine math.** Leer `paper_engine.py` (región de fills/posición/equity, ~66-240) y `domain/portfolio/portfolio.py`. Documentar en el docstring del módulo el orden exacto replicado (BUY abre/acrece con `cash -= q*p + fee`; SELL reduce/cierra con `realized += q*(p - avg_entry)` y `cash += q*p - fee`; promedio por lotes).
- [ ] **Step 2: Write failing tests** para los casos 1-9 (fixtures de eventos construidos con la misma semántica del engine; `book_equity` = `equity` del último evento).
- [ ] **Step 3: Run test to verify it fails** (`uv run pytest tests/test_accounting_reconciliation.py -q`)
- [ ] **Step 4: Implement** `reconcile_accounting` replicando el orden exacto; usar `Decimal(str(...))` para pasar de float persistido a Decimal en cada operación y que el residual del caso "idéntico" sea exactamente `0`.
- [ ] **Step 5: Run test to verify it passes** — los 9 casos en verde.
- [ ] **Step 6: `git add`**

---

### Task 4b: Reconciliación componente a componente + anti-corrupción compensada

**Files:**
- Modify: `src/application/services/accounting_reconciliation.py`
- Test: `tests/test_accounting_reconciliation.py`

**Contexto (decisión usuario 16c.6):** Task 4 probó que `residual(equity) == 0` NO es suficiente: dos corrupciones pueden compensarse (fee ↑ + qty/price ↓) y dejar la equity final intacta ⇒ falso PASS. El gate contable debe comparar **componente a componente** contra el último libro bueno persistido.

**Interfaces (añade/augmenta en el módulo):**
- `@dataclass(frozen=True, slots=True) BookState: cash: Decimal, position_qty: Decimal, average_entry: Decimal | None, realized_pnl: Decimal, fees: Decimal, equity: Decimal` + `to_dict() -> dict[str, str]` (valores `str(Decimal)`) y `from_dict(data: Mapping[str, Any]) -> BookState | None` (None si falta clave esencial).
- `@dataclass(frozen=True, slots=True) ReconciliationResult: status: str, ledger: AccountingLedger, book: BookState, mismatches: tuple[str, ...], accounting_residual: Decimal`
  - `status` = `"PASS"` si `mismatches == ()`, si no `"FAIL"`.
  - `accounting_residual` = **máximo** de los deltas absolutos de los invariantes aplicables (equity, cash, position_qty, realized_pnl, fees, avg_entry si aplica); `Decimal("0")` si PASS. Así, corrupción compensada que conserva equity pero rompe cash/position ⇒ `accounting_residual != 0` ⇒ el evaluador (que solo mira `accounting_residual == 0`) hace FAIL.
- `reconcile_with_book(events: Sequence[PaperTradeEvent], *, initial_capital: float, mark_price: float | None, previous_book: Mapping[str, Any] | None, interval_ms: int) -> ReconciliationResult`
  - Reusa el espejo del engine (Task 4). Si `previous_book is None` (primer ancla / sesión nueva / sin libro bueno previo) ⇒ `status = "PASS"` como **baseline**: no hay referencia previa, se acepta la reconstrucción actual como libro bueno (carveout explícito del usuario: corrupción histórica de estados intermedios ya inexistentes queda fuera de alcance).
  - Invariantes aplicables cuando `previous_book` existe:
    - `book.cash == ledger.cash`
    - `book.position_qty == ledger.position_qty`
    - `book.realized_pnl == ledger.realized_pnl`
    - `book.equity == ledger.reconstructed_equity`
    - `book.fees == ledger.fees`
    - si `ledger.position_qty > 0` **y** `book.average_entry is not None`: `book.average_entry == ledger.average_entry` (solo si `avg_entry` es parte fiable del libro persistido).
  - Comparación Decimal **exacta** (misma estrategia bit-exacta de Task 4). Sin tolerancias.

**Tests obligatorios nuevos:**
1. `test_compensating_corruption_fee_up_preserves_equity_fails` — parte de un `previous_book` bueno (generado con el `Portfolio` real tras 1+ fills); construye eventos alterados donde se sube una `fee` y se ajusta un `price`/`quantity` para que la **equity final coincida** con el libro; `reconcile_with_book` ⇒ `status == "FAIL"`, `accounting_residual != 0`, y `"cash"` (y/o `"realized_pnl"`) ∈ `mismatches`.
2. `test_same_final_equity_wrong_position_cash_decomposition_fails` — misma equity final pero descomposición position/cash distinta del libro (p. ej. re-partir un fill BUY 1.0 en dos BUY 0.5 con precios que compensan) ⇒ `status == "FAIL"`, `accounting_residual != 0`.
3. `test_first_write_no_previous_book_is_baseline_pass` — `previous_book=None` ⇒ `status == "PASS"`, `accounting_residual == Decimal("0")`.
4. `test_book_state_roundtrip` — `BookState(...).to_dict()` → `from_dict` → igualdad exacta.
5. Conservar los 18 tests existentes (casos 1-10 + paridad) sin debilitar asserts.

**Reglas:** no modificar la matemática del engine ni el espejo de Task 4 (sin cambios de agrupación de operandos). El resultado nuevo se construye SOBRE `reconcile_accounting` existente. Solo se tocan los dos archivos. Sin commits — final `git add` de ambos.

- [ ] **Step 1: Write failing tests** (los 4 nuevos; RED)
- [ ] **Step 2: Run to verify failure** (`uv run pytest tests/test_accounting_reconciliation.py -q`)
- [ ] **Step 3: Implement** `BookState`, `ReconciliationResult`, `reconcile_with_book`
- [ ] **Step 4: Run to verify pass** (18 existentes + 4 nuevos = 22; ruff format/check; `uv run mypy src/application/services/accounting_reconciliation.py tests/test_accounting_reconciliation.py` → 0)
- [ ] **Step 5: `git add`**

---

### Task 5: Composición del estado v2 + escritura (productor real)

**Files:**
- Modify: `src/application/services/certification_snapshot.py`
- Modify: `src/application/services/paper_runner.py` (`write_certification_state` 281-318)
- Test: `tests/test_certification_snapshot.py`

**Interfaces:**
- Produces:
  - Constante canónica en el productor: `FROZEN_VERSION_KEYS: tuple[str, ...] = ("git_commit", "application_version", "strategy_version", "risk_config_version", "docker_image_digest", "symbol", "timeframe", "initial_capital", "fees_slippage_config_version", "certification_started_at")` — usada por `_frozen_block`/`_current_block`/tests. **Un solo origen en el productor.**
  - `@dataclass(frozen=True, slots=True) OperationalFacts: accounting_residual: Decimal, recovery_integrity: str, unexplained_market_gaps: int, market_evidence_complete: str, decision_context_coverage: float, state_continuity: str, metrics_history_days: int, critical_errors: list[dict[str, Any]], certification_reports_complete: str, kill_switch_tested: str, daily_loss_tested: str, fill_count: int, closed_trade_count: int, trade_count: int`
  - `build_certification_state_v2(*, previous: Mapping[str, Any], summary: PaperRunSummary, events: Sequence[PaperTradeEvent], candles: Sequence[Candle], heartbeat_ok: bool, today: str, safeguard_evidence: Mapping[str, Any], reconciliation: ReconciliationResult, artifact: RuntimeArtifact, now_ms: int, interval_ms: int, report_path: str | None) -> dict[str, Any]`
    - Devuelve el dict v2 con `schema_version: 2`, `session_id`, `session_started_at`, `frozen` (inmutable), `current`, `operational`, `accounting_book` (el `BookState` a persistir: si `reconciliation.status == "PASS"` ⇒ el libro reconstruido actual; si `"FAIL"` ⇒ conserva el `previous["accounting_book"]` — nunca se avanza el libro con estado corrupto), `status: None`, `invalidated_reason: None`, **más** las claves legacy planas (`strategy_version`, `strategy_hash`, `active_strategy_hash`, `calendar_days`, `trade_count`, `market_regimes`, `periodic_reports`, `latest_equity`, `initial_equity`, `pnl_absolute`, `pnl_pct`) para compatibilidad de lectura.
    - `operational.accounting_residual` = `reconciliation.accounting_residual` (0 exacto ⇔ todos los invariantes coinciden; compensación ⇒ != 0 ⇒ evaluador FAIL).
    - `kill_switch_tested`/`daily_loss_tested` = `"PASS"` solo si `safeguard_passes(...)` (Task 6) con evidencia de drill COMPLETA ligada al artefacto; si no `"FAIL"`.
    - Traduce `MissingMarkError` a `operational.accounting_residual = Decimal("NaN")` + `critical_errors` (el evaluador reporta FAIL, nunca crash).
  - `write_certification_state_v2(state: dict[str, Any], state_path: Path) -> None` — **crash-safe**:
    1. `serialize` = `json.dumps(state, indent=2, sort_keys=True) + "\n"`
    2. escribir a `state_path.with_name(state_path.name + ".tmp")`
    3. `f.flush(); os.fsync(f.fileno()); f.close()`
    4. `os.replace(tmp, state_path)` (atómico)
    5. (best-effort) `os.fsync` del directorio padre.
    Un crash nunca deja un `certification-state.json` truncado que parezca válido.
- Modifica: `paper_runner.write_certification_state` mantiene su contrato legacy (callers/tests actuales) o se sustituye; decisión del implementador, sin romper `tests/test_paper_runner.py`/`test_cli_paper_runner.py`.

**Requisitos vinculantes (usuario 16c.6):**
- `schema_version = 2`; estructura `frozen`/`current`/`operational` (+ `accounting_book`).
- **Paridad de contrato, sin duplicación silenciosa (regresión 9-vs-10):** test que importa la constante real del evaluador `harness/scripts/paper_certification.py` (por ruta, `importlib.util.spec_from_file_location`) y afirma:
  `set(frozen.keys()) == set(FROZEN_VERSION_KEYS_evaluador)` y `set(current.keys()) == set(FROZEN_VERSION_KEYS_evaluador)`, con `set(producer.FROZEN_VERSION_KEYS) == set(evaluador.FROZEN_VERSION_KEYS)`.
- **Legacy (0.1.x):** estado plano legacy se lee SIN error; NUNCA se reutiliza como ancla v2; la primera escritura v2 válida recibe `certification_started_at` fresca (test explícito).
- Heartbeats: persistir `state["metrics_heartbeats"] = add_metrics_heartbeat(previous, today, artifact_ok=heartbeat_ok)` (puntero del ledger Task 3). `interval_ms`/`today` reales.
- `state_continuity` (Task 3) sobre `previous`; `recovery_integrity` (Task 3) desde `critical_errors`.

- [ ] **Step 1: Write failing tests**
  - legacy prev + 1 fill flat + velas continuas + heartbeats 30 días + safeguard compatible + `reconciliation.status == "PASS"` ⇒ dict v2: `schema_version==2`, `frozen["application_version"]=="0.2.0"`, `operational["accounting_residual"]==Decimal("0")`, claves legacy presentes, `accounting_book` persistido = libro reconstruido.
  - `set(frozen.keys()) == set(evaluador_FROZEN_VERSION_KEYS)` y `set(current.keys()) == set(evaluador_FROZEN_VERSION_KEYS)` (import por ruta del harness).
  - legacy 0.1.x plano ⇒ `frozen["certification_started_at"]` = ancla fresca (≠ ningún timestamp del legacy), nunca reutilizada.
  - `reconciliation.status == "FAIL"` (corrupción compensada) ⇒ `operational["accounting_residual"] != 0` y `accounting_book` NO avanza (conserva el previo).
  - `previous["frozen"]` compatible se conserva byte a byte entre dos llamadas con `now_ms` distinto.
  - crash-safety: tras `write_certification_state_v2`, el path tmp no existe y el contenido del archivo es exactamente el serializado.
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** `FROZEN_VERSION_KEYS`, `build_certification_state_v2`, `write_certification_state_v2`. Reutilizar `_resolve_frozen`, `_current_block` (con `started_at_iso` del frozen), kernels (Task 3), `reconcile_with_book`/`BookState` (Task 4b).
- [ ] **Step 4: Run test to verify it passes** + `tests/test_paper_runner.py` y `tests/test_cli_paper_runner.py` en verde + ruff format/check + `uv run mypy src tests` → 0 (verificar el archivo tocado al menos; el gate full en Task 9).
- [ ] **Step 5: `git add`**

---

### Task 5b: Certification clock explícito (NOT_STARTED→START) + JSON estricto sin NaN (correcciones usuario)

**Files:**
- Modify: `src/application/services/certification_snapshot.py`
- Test: `tests/test_certification_snapshot.py`

**1) Reloj de certificación explícito — NO auto-ancla en la primera escritura v2.**

Contrato de estados:

```text
NOT_STARTED
  → certification_started_at = None  (clave presente en frozen, valor null)
  → nunca puede PASS (el evaluador: age None ⇒ calendar_days FAIL)
START CERTIFICATION explícito
  → crea el anchor UTC UNA sola vez (ahora)
restart
  → conserva exactamente el anchor
segunda escritura
  → reutiliza el anchor, NO re-ancla
legacy 0.1.x
  → nunca aporta anchor v2
INVALIDATED + nuevo START
  → crea un anchor nuevo
```

Cambios de interfaz (producer):
- `certification_phase(state: Mapping[str, Any]) -> str` → `"NOT_STARTED"` (sin `frozen.certification_started_at` con valor), `"RUNNING"` (anchor presente y `status != "INVALIDATED"`), `"INVALIDATED"` (`status == "INVALIDATED"`).
- `_resolve_frozen(previous, artifact)` **deja de anclar**: si `previous.frozen` compatible ⇒ lo conserva; si no (ausente / legacy / NOT_STARTED) ⇒ frozen con `certification_started_at = None` (10 claves, valor null). NUNCA fija un anchor por el simple hecho de escribir.
- `start_certification(previous: Mapping[str, Any], artifact: RuntimeArtifact, *, now_ms: int) -> dict[str, Any]`:
  - estado `NOT_STARTED` o sin frozen compatible ⇒ produce copia con `frozen.certification_started_at = _iso_utc_ms(now_ms)` (anchor nuevo).
  - estado `RUNNING` con frozen compatible (mismo symbol/timeframe/application_version/strategy_version) ⇒ **no-op** (NO re-ancla).
  - estado `INVALIDATED` ⇒ produce estado nuevo con anchor fresco (`_iso_utc_ms(now_ms)`), reemplazando el frozen previo.
- `build_certification_state_v2` ya NO recibe `now_ms` como ancla implícita: compone `current` con `started_at_iso = frozen["certification_started_at"]` si RUNNING, o `None` si NOT_STARTED. `frozen`/`current` mantienen las 10 claves (valor null en NOT_STARTED) para preservar la paridad de contrato.
- El ancla solo se materializa vía `start_certification` (operador / CLI del runner en Task 7). `current.certification_started_at` debe reflejar `frozen.certification_started_at` (null en NOT_STARTED) para no inducir drift.

Tests mínimos (obligatorios, en `tests/test_certification_snapshot.py`):
1. `periodic write before start → no inicia reloj`: `build_certification_state_v2` con `previous` legacy/ausente produce `frozen["certification_started_at"] is None` y `certification_phase(...) == "NOT_STARTED"`.
2. `explicit start → anchor creado`: `start_certification` sobre NOT_STARTED ⇒ `certification_started_at == _iso_utc_ms(now)`.
3. `second start while RUNNING → no re-anchor`: dos `start_certification` con `now` distinto sobre estado RUNNING ⇒ anchor del primero se conserva.
4. `restart → mismo anchor`: estado v2 RUNNING guardado, recargado como `previous` y recompuesto ⇒ anchor byte-idéntico.
5. `invalidate + new start → nuevo anchor`: `status=INVALIDATED` ⇒ `start_certification` produce anchor distinto del previo.
6. `legacy 0.1.x → nunca aporta anchor v2`: tras escritura v2 sobre legacy, `certification_phase == "NOT_STARTED"` (requiere START explícito para correr).
7. actualizar los tests previos de Task 2/5 que asumían auto-ancla (p. ej. `test_resolve_frozen_legacy_prev_anchors_fresh`) a la nueva semántica NOT_STARTED→START.

**2) JSON estricto — nunca NaN/Infinity/-Infinity.**

- Para errores como `MissingMarkError`, el estado NO lleva `Decimal("NaN")`: la firma de `build_certification_state_v2` gana `reconciliation: ReconciliationResult | None = None` y `reconciliation_error: str | None = None`. Cuando `reconciliation_error` (p. ej. `"missing_persisted_mark"`) está presente:
  - `operational["accounting_residual"] = None`
  - `operational["accounting_status"] = "FAIL"`
  - `operational["accounting_failure_reason"] = reconciliation_error`
  - se añade un `critical_errors` `{"message": reconciliation_error, "explained": False}`
  - `accounting_book` NO avanza.
- Cuando la reconciliación es FAIL por mismatches finitos (corrupción compensada): `accounting_residual` = str del máximo delta (numérico finito, != 0), `accounting_status = "FAIL"`, `accounting_failure_reason = "accounting_mismatch"`, libro no avanza.
- `accounting_status`/`accounting_failure_reason` van dentro de `operational` (el evaluador ignora claves extra; su check usa `accounting_residual`).
- **Guardia de finitud:** ninguna escritura v2 puede contener valores no-finitos (`float`/`Decimal` NaN, ±Infinity) en ningún campo numérico. Donde un valor de origen no sea finito, se emite `null` (o se omite) según semántica; nunca la cadena `"NaN"`.
- Test obligatorio: `json.dumps(estado_v2, allow_nan=False)` no lanza y el dump no contiene `NaN`/`Infinity` (también sobre un estado producido con `reconciliation_error="missing_persisted_mark"`).
- Actualizar el mapeo previo "libro presente-ilegible" (antes NaN) a: residual `None` + `accounting_status="FAIL"` + reason `"unparseable_accounting_book"`.

**Reglas:** no tocar el evaluador (`harness/scripts/paper_certification.py`), ni la matemática del engine. `reconcile_with_book` sigue devolviendo solo deltas finitos (no produce NaN). Mantener 10-key parity, crash-safe write y legacy tests vigentes. Solo se tocan los dos archivos. Sin commits — final `git add`.

- [ ] **Step 1: Write failing tests** (los 7 de reloj + finitud + estricto-json; actualizar los que asumían auto-ancla)
- [ ] **Step 2: Run to verify failure** (`uv run pytest tests/test_certification_snapshot.py -q`)
- [ ] **Step 3: Implement** `certification_phase`, `start_certification`, `_resolve_frozen` sin auto-ancla, `build_certification_state_v2` con `reconciliation_error` + guardia de finitud.
- [ ] **Step 4: Run to verify pass** — suite completa de producto (`uv run pytest -q`), ruff format/check, `uv run mypy src tests` → 0. Confirmar que `tests/test_e2e_restart_parity.py` y suites legacy siguen verdes.
- [ ] **Step 5: `git add`**

---

### Task 6: Safeguard evidence — drill operativo por secuencias + matcher fail-closed

**Files:**
- Create: `harness/scripts/safeguard_drill.py` (CLI del operador; **fuera** de PaperRunner/RiskEngine/Portfolio — no introduce caminos especiales en el producto)
- Modify: `src/application/services/certification_snapshot.py` (matcher `safeguard_passes`)
- Test: `harness/tests/test_safeguard_drill.py`, `tests/test_certification_snapshot.py`

**Restricción de aislamiento (harness):** el drill importa guardas reales del dominio puro del producto (`domain.risk.guards`, `domain.risk.config`, `domain.time.*` si aplica) añadiendo `repo/src` a `sys.path` al arranque (verificado: harness python 3.12 importa `domain` puro sin dependencias externas). El drill NO importa `application.services.paper_engine` si eso arrastra dependencias ausentes en harness; si la secuencia real exige lógica del engine, se replica la llamada exacta al guard que el engine usa (verificar en `paper_engine.py` qué guard decide rechazar BUY) y se documenta. **No fabricar** semántica que el producto real no tenga.

**Secuencias que debe demostrar la evidencia (no flags cosméticos):**

Kill switch:
1. `KillSwitch().activate(reason=..., timestamp_ms=T)`
2. intento de BUY → **rechazado porque kill switch activo** (vía `allows_trading()` = False, el mismo guard que consulta el engine)
3. persistencia del estado (`KillSwitchState.to_dict()` → JSON del evidence/drill)
4. "restart" (instanciar `KillSwitch` desde `KillSwitchState.from_dict(...)`)
5. sigue activo → BUY sigue rechazado
6. `reset(by="human")` explícito del operador
7. cada paso registrado; solo PASS si la secuencia completa se cumple en orden.

Daily loss:
1. umbral de daily loss alcanzado (`daily_loss_exceeded(realized=-capital*max_daily_loss, ...)` = True)
2. BUY rechazado
3. SELL sigue permitido
4. "restart" conserva el estado daily-loss (verificar cómo el producto persiste/reconstruye el daily loss entre reinicios: si se re-deriva de eventos del día, reflejarlo fielmente)
5. UTC rollover → la restricción se resetea correctamente (usar el mismo criterio de día del producto: `domain/time/*`)
6. cada paso registrado; PASS solo si secuencia completa.
**Si el producto real NO conserva daily-loss entre reinicios (o no resetea por UTC), el drill debe reportar ese hallazgo y NO emitir PASS** (evidencia veraz; hallazgo productivo para el checkpoint, nunca falsa PASS).

**Evidencia (JSON, ruta `settings.paper_safeguard_evidence_path` por defecto) — cada drill válido registra UNA secuencia completa:**
```json
{"type": "kill_switch", "status": "PASS", "at_iso": "...Z",
 "steps": ["activate", "buy_rejected", "persist", "restart_still_active", "buy_still_rejected", "operator_reset"],
 "artifact": {"git_commit": "...", "application_version": "0.2.0",
              "docker_image_digest": "sha256:...", "strategy_version": "baseline-v1",
              "risk_config_version": "risk-v1"}}
```
Exit 0 solo si `status == "PASS"`; escritura atómica (fsync + `os.replace`); preserva entradas previas.

**Matcher (producer) `safeguard_passes(safeguard_evidence, kind, frozen) -> bool` — fail-closed:** PASS solo si existe una entrada con `type == kind`, `status == "PASS"`, `steps` == la secuencia completa esperada para `kind`, y las 5 claves de `artifact` coinciden exactamente con `frozen` (comparación normalizada int↔float↔str trim). Casos: evidencia ausente ⇒ False; mismatch de artefacto (git/version/digest/strategy) ⇒ False; mismatch de risk_config_version ⇒ False; drill incompleto (falta step) ⇒ False; PASS exacto ⇒ True.

**Momento (proceso):** el drill se ejecuta ANTES de crear la nueva certificación; sus fills/rechazos no forman parte de la sesión pasiva de 30 días (no escriben `paper_trade_events` de la sesión). Evidencia PASS + artefacto exacto ⇒ la certificación puede comenzar.

- [ ] **Step 1: Write failing tests**
  - `harness/tests/test_safeguard_drill.py`: secuencia kill_switch completa ⇒ escribe evidencia PASS (steps completos); drill incompleto (step faltante) ⇒ NO PASS/exit≠0; daily-loss rollover resetea.
  - `tests/test_certification_snapshot.py`: `safeguard_passes` — evidencia ausente ⇒ False; artifact mismatch (git_commit/docker_image_digest/strategy_version) ⇒ False; risk_config_version mismatch ⇒ False; steps incompletos ⇒ False; PASS exacto ⇒ True.
- [ ] **Step 2: Run to verify failure** (`cd harness && uv run pytest tests/test_safeguard_drill.py -q` y `uv run pytest tests/test_certification_snapshot.py -q`)
- [ ] **Step 3: Implement** `harness/scripts/safeguard_drill.py` (sys.path a repo/src; secuencias reales; verificar en `paper_engine.py` el guard usado para rechazar BUY y en `domain/time/*` el criterio de día/rollover) y `safeguard_passes` en `certification_snapshot.py`.
- [ ] **Step 4: Run to verify pass** — harness suite (`cd harness && uv run pytest tests/test_safeguard_drill.py -q`) + producto (`tests/test_certification_snapshot.py -q`); ruff format/check en ambos árboles; `uv run mypy src` 0 (producto).
- [ ] **Step 5: `git add`** (ambos árboles)

---

### Task 7: Wiring real en el paper-runner (_run_loop)

**Files:**
- Modify: `src/interfaces/cli/paper_runner.py`
- Test: `tests/test_cli_paper_runner.py`, `tests/test_paper_runner.py`

**Interfaces:**
- Consumes: `build_certification_state_v2`, `write_certification_state_v2`, `runtime_artifact`, `session_started_at_ms`, `certification_phase`/`start_certification` (Task 5b), `reconcile_with_book`/`latest_persisted_mark`/`MissingMarkError` (Tasks 4b), `reconciliation_error` (Task 5b).
- Cambios:
  - **START explícito:** el CLI del paper-runner gana un flag `--start-certification` (operador). En `_run(...)`/`run_paper_runner(...)`, antes del bucle y solo con el flag: cargar `previous = load_certification_state(state_path)`; si `certification_phase(previous) == "NOT_STARTED"` o `"INVALIDATED"` ⇒ `start_certification(previous, artifact, now_ms=now)` y `write_certification_state_v2`. Idempotente: si `RUNNING` ⇒ no-op (no re-ancla). Sin el flag, el runner NUNCA inicia el reloj (NOT_STARTED persistido).
  - `_run_loop(...)`: en el bloque periódico (hoy `cli/paper_runner.py:204-227`) ya dispone de `events`, `summary`, `runner.regime_evidence()`. Añadir parámetros `candle_repo: MarketCandleRepository`, `artifact: RuntimeArtifact`, `heartbeat_ok` (resultado de un self-scrape a `http://127.0.0.1:{paper_metrics_port}/metrics`), y `state_path`. Construir el estado v2 con `previous = load_certification_state(state_path)`, `events`, `candles = await candle_repo.session_range(session_id, symbol, timeframe, 0, now_ms)`, `safeguard_evidence = json.loads(settings.paper_safeguard_evidence_path)` (con try/except → `{}`), `today` (UTC `YYYY-MM-DD`), `now_ms`, `interval_ms` (de `timeframe`); **reconciliación**:
    ```python
    try:
        reconciliation = reconcile_with_book(
            events, initial_capital=RiskConfig().capital,
            mark_price=latest_persisted_mark(candles),
            previous_book=previous.get("accounting_book"), interval_ms=interval_ms,
        )
        reconciliation_error = None
    except MissingMarkError:
        reconciliation = None
        reconciliation_error = "missing_persisted_mark"
    ```
    y llamar `build_certification_state_v2(..., reconciliation=reconciliation, reconciliation_error=reconciliation_error, ...)`; escribir con `write_certification_state_v2`. **Fail-closed:** si la construcción del estado falla por cualquier error inesperado, se registra el error y NO se inventa evidencia ni se altera el comportamiento de trading.
  - `_run(...)`: construir `artifact = runtime_artifact(...)` con `settings.app_version`, `settings.git_commit`, `settings.docker_image_digest`, `RiskConfig()`, y pasarlo a `_run_loop`; añadir `candle_repo` al hilo.
  - El ancla: **nunca** se inicia por una escritura periódica; solo `--start-certification` (Task 5b). El runner preserva el anchor de `previous` en restart; segunda escritura reutiliza; legacy no aporta anchor; tras INVALIDATED + nuevo `--start-certification` se crea anchor nuevo.
- Regla: los self-scrapes fallidos NO abortan el runner: `heartbeat_ok=False` (ese día no cuenta cobertura). Los errores críticos (commit failure / `RecoveryDivergenceError`) se añaden a `critical_errors` persistido con `{"message", "kind", "at_ms", "explained": False}`. El `accounting_book` avanza solo cuando `reconciliation.status == "PASS"` (lo garantiza `build_certification_state_v2`).

- [ ] **Step 1: Write failing tests** (CLI con repos in-memory):
  - una corrida periódica SIN flag produce estado `schema_version == 2` con `certification_phase == "NOT_STARTED"` y claves legacy presentes;
  - una corrida con `--start-certification` produce `certification_phase == "RUNNING"` con anchor ISO; una segunda con el flag y distinto `now_ms` NO re-ancla (anchor idéntico);
  - restart: recargar estado RUNNING y recomponer ⇒ mismo anchor;
  - INVALIDATED + nuevo `--start-certification` ⇒ anchor nuevo;
  - dos corridas periódicas con distinto `now_ms` conservan `frozen` idéntico;
  - con repos sin velas y posición abierta ⇒ estado con `operational["accounting_residual"] is None`, `accounting_status == "FAIL"`, `failure_reason == "missing_persisted_mark"`, `json.dumps(estado, allow_nan=False)` OK, y sin crash.
- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** el wiring (arriba). Reutilizar `load_certification_state`. No alterar trading behavior.
- [ ] **Step 4: Run to verify pass** + `uv run pytest tests/test_cli_paper_runner.py tests/test_paper_runner.py -q` y producto completo.
- [ ] **Step 5: `git add`**

---

### Task 8: E2E productor → JSON → evaluador (mismo productor)

**Files:**
- Create: `tests/e2e/test_certification_state_v2_e2e.py`
- Test: el propio archivo

**Objetivo (requisito clave 16c.6):** el E2E usa `build_certification_state_v2` (el MISMO productor del paper-runner) sobre un escenario sembrado en repos in-memory; escribe el JSON a disco con `write_certification_state_v2`; invoca el evaluador real `harness/scripts/paper_certification.py` (`main` o `evaluate_certification`) sobre ese archivo; comprueba el resultado.

**Casos obligatorios E2E (productor real, NUNCA JSON v2 construido a mano):**

Helper de recorrido: sembrar eventos/velas in-memory; recorrer el tiempo llamando `build_certification_state_v2` (con `write_certification_state_v2` a disco) para cada día: día 0 sin `start_certification` ⇒ NOT_STARTED; luego `start_certification` en t0 (ancla); heartbeats diarios (`heartbeat_ok=True`, `today` distinta); reconciliación con libro (día 0 `previous_book=None` → baseline; avanza `accounting_book` con PASS). Evaluar con el evaluador REAL importado por ruta (`harness/scripts/paper_certification.py`). `strategy_version="baseline-v1"`, `risk_config_version="risk-v1"`. No tocar matemática de trading/risk.

1. **RUNNING + age 30d + metrics 30d + evidencia completa → PASS**: evaluar en `t0+30d` ⇒ `overall_status == "PASS"`, `certification_age_days >= 30.0`.
2. **age 29d → FAIL**: evaluar en `t0+29d` ⇒ `FAIL` (calendar_days).
3. **age 30d + metrics 29d → FAIL**: 30 días de reloj pero solo 29 heartbeats ⇒ `FAIL` (metrics_history_days).
4. **Corrupción contable compensada → FAIL con razón contable preservada**: tras avanzar `accounting_book` (día ≥1), alterar `fee↑` + `price↓` conservando equity final bit-igual ⇒ `operational["accounting_residual"] != 0`, `accounting_status == "FAIL"`, `accounting_failure_reason == "accounting_mismatch"` y evaluador `FAIL`.
5. **Safeguard evidence artifact mismatch → FAIL**: entrada de safeguard con `risk_config_version` (u otra clave) distinta ⇒ `kill_switch_tested`/`daily_loss_tested == "FAIL"` y evaluador `FAIL`.
6. **Version drift → FAIL**: a partir del día 30, artefacto con `strategy_version` distinta en `current` (misma sesión) ⇒ `frozen_versions` FAIL (el anchor no se re-ancla).
7. **NOT_STARTED → nunca PASS**: estado v2 sin `start_certification` (anchor `None`), evaluado a cualquier edad ⇒ `FAIL` (calendar_days) — jamás PASS.
8. **JSON estricto → sin NaN/Infinity**: sobre cada estado producido (incl. caso 4 y el de `reconciliation_error="missing_persisted_mark"`), `json.dumps(estado, allow_nan=False)` no lanza y el dump no contiene `NaN`/`Infinity`/`-Infinity`.

**Regla anti-manual:** ningún caso construye `frozen`/`current`/`operational` a mano; todo sale de `build_certification_state_v2` (el MISMO del paper-runner desplegado).

- [ ] **Step 1: Write the E2E tests** (los 8 casos; helpers reutilizando fixtures/repos in-memory de `tests/e2e/`).
- [ ] **Step 2: Run to verify FAIL** (`uv run pytest tests/e2e/test_certification_state_v2_e2e.py -q`)
- [ ] **Step 3: Implement/habilitar** lo que falte en productor/wiring para que el E2E pase (si un escenario revela defecto real en ejecución/recovery: **detenerse y reportar**, no parchear la matemática).
- [ ] **Step 4: Run to verify PASS** — E2E completo en verde + suite completa de producto.
- [ ] **Step 5: `git add`**

---

### Task 8b: Correcciones pre-Task-9 (A identidad al START, B routing legacy/v2 por schema, C matcher `type==kind`)

**Files:**
- Modify: `src/application/services/certification_snapshot.py` (A+C), `src/interfaces/cli/paper_runner.py` (A+B)
- Test: `tests/test_certification_snapshot.py`, `tests/test_cli_paper_runner.py`

**A) BLOCKER — identidad al START (sesión prístina).** Resolver identidad del artifact como:
`persisted/session value si existe, ELSE config (symbols[0], timeframe.label)`.
En el runner, el artifact para `--start-certification` y para cada escritura v2 se construye con `symbol`/`timeframe`/`strategy_version` que vengan de (1) el resumen de sesión persistido si no vacíos, o (2) la configuración (`symbols[0]`, `timeframe.label`, `EmaRsiBaseline.version`) — NUNCA vacíos por 0 eventos. `start_certification` valida que los 8 campos obligatorios del artifact estén no vacíos (`symbol`, `timeframe`, `git_commit`, `application_version`, `strategy_version`, `risk_config_version`, `docker_image_digest`, `fees_slippage_config_version`); si falta alguno ⇒ **START rejected**: no crea anchor (`certification_started_at` sigue `None`), estado NOT_STARTED, y (si el caller es CLI) se registra/loguea el rechazo.
Tests: pristine + config válida ⇒ START correcto con anchor; restart ⇒ misma identidad + mismo anchor; identidad persistida ≠ config ⇒ FAIL (no empieza/avisa, no ancla con identidad inconsistente); falta un campo obligatorio ⇒ no START (anchor None).

**B) Routing legacy/v2 por schema (NO por parámetros de wiring).** En `_run_loop`, la decisión de qué escritor usar se basa en el ARCHIVO: si no existe el fichero o `previous["schema_version"] == 2` ⇒ v2; si el fichero existe y no trae `schema_version`/es legacy plano ⇒ **legacy compatibility** (`write_certification_state`). Eliminar el fallback por "parámetros v2 ausentes" como criterio.

**C) Safeguard matcher.** `safeguard_passes` exige además `entry["type"] == expected_kind`; mismatch ⇒ False (fail-closed). Test de tipo mismatch.

Sin commits — `git add` de los archivos tocados.

- [ ] **Step 1: Write failing tests** (A: 4 casos; B: fichero v2→v2, legacy→legacy, ausente→v2; C: type mismatch)
- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** A (identity resolver + validación START), B (routing por schema), C (matcher type==kind)
- [ ] **Step 4: Run to verify pass** — producto completo + ruff format/check + `uv run mypy src tests` 0
- [ ] **Step 5: `git add`**

---

### Task 8c: Fixes whole-branch review — F1 (start → schema v2 completo) y F2 (reconciliación three-way con checkpoint)

**Files:**
- Modify: `src/application/services/certification_snapshot.py` (F1: `start_certification` emite doc v2 completo)
- Modify: `src/interfaces/cli/paper_runner.py` (F1 regression / limpieza si aplica)
- Modify: `src/application/services/accounting_reconciliation.py` (F2: three-way)
- Test: `tests/test_accounting_reconciliation.py`, `tests/test_certification_snapshot.py`, `tests/test_cli_paper_runner.py`, `tests/e2e/test_certification_state_v2_e2e.py`

**F1 (GATE usuario):** `start_certification` debe escribir directamente un estado **`schema_version: 2` completo** (envelope con `session_id`, `session_started_at`, `frozen` con anchor, `current`, `operational` presente, `status: None`, `accounting_book` presente) — NO depender de heurística `{frozen,current} => v2`. Añadir regresión: `fresh start → periodic write → operational v2 presente` (camino deploy fresco). Mantener routing por `schema_version` (Task 8b).

**F2 (GATE usuario):** reemplazar el libro estático por **reconciliación three-way**:
```text
current live book (equity persistida del último evento)
    ==
full reconstruction (todos los eventos persistidos)
    ==
incremental reconstruction (checkpoint previo + events_since por cursor)
```
Comparar **component-wise** cash / position_qty / avg_entry / realized_pnl / fees / equity. Para posición abierta, calcular equity de los tres caminos con el **mismo último mark persistido confirmado** (no consulta live). El **checkpoint guarda cursor + estado contable y solo avanza en PASS**.

Cambios:
- `BookState` gana `last_event_ms: int | None` (cursor). `from_dict` tolerante: sin cursor ⇒ baseline (re-baseline documentado: nunca desplegado, sin migración real).
- `reconcile_with_book(events, *, initial_capital, mark_price, previous_checkpoint, interval_ms)`:
  - `previous_checkpoint is None` (o ilegible sin cursor) ⇒ baseline PASS; checkpoint = mirror completo + cursor = último `timestamp_ms`.
  - si no: `events_since` = eventos con `timestamp_ms > checkpoint.last_event_ms`; `incremental` = avanzar el checkpoint con `events_since` (misma aritmética espejo); `full` = mirror sobre todos los eventos; `live` = equity del último evento.
  - `mismatches` sobre comparaciones: (a) full vs incremental por componente (cash/qty/avg_entry si posición abierta/realized/fees/equity) — detecta corrupción/borrado de eventos viejos; (b) equity reconstruida (full/incremental, mismas) vs `live` con el mismo mark — detecta corrupción de eventos nuevos y borrado del último.
  - `accounting_residual` = max delta entre todos los caminos aplicables; PASS ⇔ 0.
- El productor persiste `accounting_book` = checkpoint solo cuando PASS (con cursor actualizado); FAIL conserva el checkpoint previo.

Tests obligatorios (F2): (1) fill legítimo entre writes ⇒ PASS y checkpoint avanza; (2) segundo write sin eventos ⇒ sigue PASS; (3) mark drift con posición abierta ⇒ PASS (misma marca para los tres caminos); (4) corrupción de evento viejo ⇒ FAIL; (5) corrupción de evento nuevo ⇒ FAIL; (6) evento borrado ⇒ FAIL; (7) corrupción compensada ⇒ FAIL; (8) restart + nuevos fills ⇒ PASS (checkpoint recargado + evento nuevo ⇒ PASS y avanza).
Actualizar tests previos que asumían el libro estático (Task 4b) a la semántica three-way sin debilitar asserts de corrupción. Mantener: matemática del engine intacta, Decimal exacto, strict-JSON/no-NaN, E2E 8 casos (caso 4 compensada debe seguir FAIL con reason `accounting_mismatch`).

- [ ] **Step 1: Write failing tests** (F1 regression + 8 F2)
- [ ] **Step 2: Run to verify failure**
- [ ] **Step 3: Implement** F1 y F2
- [ ] **Step 4: Run to verify pass** — producto completo + ruff + mypy + E2E
- [ ] **Step 5: `git add`**

---

### Task 9: Bump 0.2.0 + Quality gates + Ledger + Whole-branch review + Commit Candidate final

**Files:**
- Modify: `src/version.py` (`0.1.3` → `0.2.0`), `pyproject.toml` (version → `0.2.0`)
- Create: `tests/test_version_consistency.py` (anti-drift: `__version__` de `src/version.py` == `[project].version` de `pyproject.toml` == `"0.2.0"`)
- Create: `docs/phases/16c/ledger-16c.md` (estado 16c.1..16c.5 COMPLETE, **16c.6 READY_FOR_COMMIT_GATE**; NO marcar Paper certificado)
- Create: `docs/phases/16c/commit-candidate-007.md` (Commit Candidate FINAL 16c.6 → **estado READY_FOR_USER_GATE**)
- Modify: `docs/phases/16c/evidence/log.md` (+ `post-commit-verification-004.md`/`006.md` ya creados como carry-over documental)

**Steps:**
- [ ] **Step 1:** Whole-branch review: revisión completa `66448dc..workspace` (dispatch code review del diff total) con triage de todos los deferred minors del ledger; resolver en un fix wave lo que la review marque antes de merge. Evidencia del paquete de diff en `.superpowers/sdd/.../final-review/`.
- [ ] **Step 2:** Bump versiones (`src/version.py` y `pyproject.toml` → `0.2.0`) + test anti-drift `tests/test_version_consistency.py`.
- [ ] **Step 3:** Ledger 16c (`docs/phases/16c/ledger-16c.md`): 16c.1 COMPLETE · 16c.2 COMPLETE · 16c.3 COMPLETE · 16c.4 COMPLETE · 16c.5a COMPLETE · 16c.5 COMPLETE · **16c.6 READY_FOR_COMMIT_GATE**. **No marcar Paper como certificado.** Nota: `add-phase`/`progress.yaml` del tronco (`feature/phase-08-llm-decision-agent`, `3e8d15f`) queda como carry-over post-merge; verificar `python3 harness/scripts/progress.py report` y no editar `progress.yaml` a mano.
- [ ] **Step 4:** Quality gates (registrar cada uno con `harness/scripts/evidence.sh 16c <nombre> -- <comando>`):
  ```bash
  # full product suite + coverage
  uv run pytest --cov=src --cov-branch --cov-report=term-missing --cov-report=json:docs/phases/16c/evidence/full-suite-coverage-16c6.json --cov-fail-under=90 -q
  # full harness suite + coverage
  cd harness && uv run pytest tests --cov=scripts --cov-branch --cov-fail-under=80 -q
  # E2E producer->state->evaluator
  uv run pytest tests/e2e/test_certification_state_v2_e2e.py -q
  # lint / format / typing
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy src tests
  # secret scan
  # (grep de credenciales en archivos tocados -> 0)
  # strict JSON validation (test dedicado ya en suite) + version consistency (test anti-drift)
  # migration chain validation: comprobar cadena de migraciones Alembic (heads/upgrade --sql o up/down si hay DB disponible; si no hay Postgres local: validar `alembic heads` + `history` y registrar evidencia MANUAL/skip con motivo)
  ```
- [ ] **Step 5:** codebase-memory: re-index del worktree, `detect_changes since 66448dc` (blast radius), `check_index_coverage` sobre CADA archivo tocado.
- [ ] **Step 6:** Redactar `docs/phases/16c/commit-candidate-007.md` COMPLETO (plantilla): objetivo, rama, archivos, diff `66448dc..workspace`, arquitectura, tests, cobertura exacta, ruff/mypy, secretos 0, blast radius, riesgos, deuda, mensaje propuesto. Estado final del entregable: **READY_FOR_USER_GATE**.
- [ ] **Step 7:** Presentar Commit Candidate al usuario y esperar GATE (nada de commit/push/merge/redeploy/Paper Certification/productivo sin APPROVED).



---

## Self-Review

**1. Spec coverage (alcance 16c.6 del usuario):**
- 1. Producer real schema v2 → Tasks 2, 3, 4, 5, 7.
- 2. `frozen` (10 campos) → Task 2 (`FROZEN_VERSION_KEYS`, `_frozen_block`).
- 3. `operational` (11 campos + counts) → Tasks 3, 4, 4b, 5.
- 3b. Anti-corrupción compensada (componente a componente, libro bueno previo) → Task 4b + Task 5 (`accounting_book` solo avanza con PASS).
- 3c. Paridad de contrato 10 frozen keys sin duplicación silenciosa → Task 5 (test vs `FROZEN_VERSION_KEYS` del evaluador por ruta).
- 3d. Escritura crash-safe (fsync + atomic replace) → Task 5.
- 3e. Safeguard drills por secuencias completas + matcher fail-closed (harness) → Task 6.

**2. Placeholder scan:** La única referencia abierta deliberada es la aritmética exacta del engine en Task 4 (se fija leyendo `paper_engine.py`/`portfolio.py` en el Step 1 de la propia Task antes de escribir tests); el resto de interfaces son exactas. Sin TBD/TODO.

**3. Type consistency:** `RuntimeArtifact`, `_resolve_frozen`, kernels (Task 3), `OperationalFacts`, `BookState`/`ReconciliationResult`/`reconcile_with_book` (Task 4b), `FROZEN_VERSION_KEYS` + `build_certification_state_v2` + `write_certification_state_v2` (Task 5), `safeguard_passes` (Task 6) se referencian con la misma firma en todas las Tasks. Nombres de repositorio/port verificados: `MarketCandleRepository.session_range/range`, `PaperTradeEventRepository.list_session`, `Candle`, `PaperTradeEvent` (campos), `RiskConfig.version/capital`, `FeeModel().version`, `SlippageModel().version`, `src/version.py.__version__`.

**Riesgo registrado (no bloqueante):** la reconciliación bit-exacta (Task 4/4b) exige replicar el orden float del engine; si los fixtures revelan una diferencia sistemática pequeña, la resolución es ajustar el ORDEN replicado (no tocar el engine) y documentarlo. El ancla 0.2.0 invalida cualquier certificación 0.1.x previa por diseño. **Task 6:** si el producto real NO conserva el daily-loss entre reinicios o no lo resetea por UTC, el drill reporta el hallazgo y NO emite PASS (evidencia veraz; nunca fabricada).
