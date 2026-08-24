# Fase 08 — LLM Decision Agent: Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea a tarea. Los pasos usan sintaxis checkbox (`- [ ]`).

**Goal:** Implementar el LLM Decision Agent con dominio independiente del proveedor, salida estructurada validada por Pydantic, fail-safe HOLD total, coste medido y presupuestado, y versionado de prompts/experimentos (PRD §17–20, §37–39, §60).

**Architecture:** Hexagonal. El dominio (`domain/trading/decision.py`, `domain/llm/*`) es puro e inmutable. El puerto `LLMProvider` (Protocol) vive en `application/ports/llm.py`; el servicio `DecisionAgent` orquesta prompt→provider→coste→fail-safe. El adapter `DeepSeekProvider` (infrastructure) habla HTTP y valida con Pydantic. El LLM **no** especifica cantidades ni toca riesgo.

**Tech Stack:** Python 3.12, dataclasses (dominio puro), Pydantic v2 (validación de salida), httpx (adapter), pytest + pytest-asyncio + MockTransport (sin LLM real en CI).

## Global Constraints

- `requires-python = ">=3.12,<3.13"` (pyproject.toml).
- Dominio puro: **cero I/O, cero frameworks** en `src/domain/` (solo `dataclasses`, `enum`, `hashlib`, `json` stdlib permitidos).
- Pydantic SOLO en `infrastructure/` (schemas), jamás en dominio.
- Docstrings en español, convención del repo. Ruff line-length 100, mypy `strict = true`.
- El LLM no puede especificar montos monetarios ni tocar riesgo (PRD §19).
- Modelo por defecto: `deepseek-v4-flash` (PRD §18).
- Fail-safe (PRD §20): timeout / API caída / presupuesto agotado / JSON inválido / schema inválido / confidence fuera de rango / respuesta incompleta / modelo no disponible ⇒ **HOLD**.
- Presupuestos: alerts 50/75/90%, bloqueo a 100% (PRD §60).
- `Action`/`Intensity` ya existen en `domain/trading/signal.py` (valores lowercase); reutilizar, no duplicar.
- NO commit sin autorización explícita (AGENTS.md §7, flujo-commits). Cada tarea deja el cambio en staging + Commit Candidate Report; el commit se ejecuta solo tras APPROVED del usuario.
- `MarketState` ya existe en `domain/market/state.py`.

---

### Task 1: Contrato de decisión (dominio puro)

**Files:**
- Create: `src/domain/trading/decision.py`
- Create: `src/domain/memory/memory.py`
- Test: `tests/test_decision.py`

**Interfaces:**
- Consumes: `domain.trading.signal.Action`, `domain.trading.signal.Intensity` (ya existen).
- Produces:
  - `DecisionContext(symbol: str, timestamp_ms: int, experiment_id: str = "", prompt_version: str = "", market_state_hash: str = "")`
  - `TradingDecision(timestamp_ms: int, action: Action, confidence: float, intensity: Intensity = Intensity.MEDIUM, rationale_summary: str = "", supporting_factors: tuple[str, ...] = (), risk_factors: tuple[str, ...] = (), fallback_reason: str | None = None)`
  - `TradingDecision.is_fallback -> bool` (property)
  - `TradingDecision.hold(timestamp_ms: int, reason: str) -> TradingDecision` (classmethod)
  - `TradingMemory(id: str, text: str, outcome_timestamp_ms: int, embedding: tuple[float, ...] = ())`

- [ ] **Step 1: Escribir el test que falla** — `tests/test_decision.py`

```python
from domain.trading.decision import DecisionContext, TradingDecision
from domain.trading.signal import Action, Intensity


def test_decision_factory_and_defaults() -> None:
    d = TradingDecision(timestamp_ms=1000, action=Action.BUY, confidence=0.73)
    assert d.action is Action.BUY
    assert d.intensity is Intensity.MEDIUM
    assert d.supporting_factors == ()
    assert d.fallback_reason is None
    assert d.is_fallback is False


def test_hold_is_fallback() -> None:
    d = TradingDecision.hold(timestamp_ms=5, reason="budget_exhausted")
    assert d.action is Action.HOLD
    assert d.confidence == 0.0
    assert d.is_fallback is True
    assert d.fallback_reason == "budget_exhausted"


def test_context_defaults() -> None:
    c = DecisionContext(symbol="ETHUSDT", timestamp_ms=42)
    assert c.prompt_version == ""
    assert c.market_state_hash == ""
```

- [ ] **Step 2: Ejecutar para verificar fallo** — `uv run pytest tests/test_decision.py -v` → FAIL (module not found).
- [ ] **Step 3: Implementar** `src/domain/trading/decision.py` y `src/domain/memory/memory.py` (dataclasses frozen slots, imports de `domain.trading.signal`).
- [ ] **Step 4: Ejecutar para verificar paso** — `uv run pytest tests/test_decision.py -v` → PASS.
- [ ] **Step 5: Staging + reporte** (commit diferido — ver flujo-commits).

---

### Task 2: Puerto `LLMProvider` + `PromptStore` + `DecisionResult`

**Files:**
- Create: `src/application/ports/llm.py`
- Test: `tests/test_llm_ports.py`

**Interfaces:**
- Consumes: `MarketState`, `TradingMemory`, `DecisionContext`, `TradingDecision`, `LLMCallRecord` (Task 3), `Prompt` (Task 3). Para no romper el orden, esta tarea define el Protocol con las importaciones finales; los módulos de dominio de la Task 3 se crean antes de ejecutar tests de esta tarea (ver nota en Step 1).
- Produces:
  - `DecisionResult(decision: TradingDecision, call: LLMCallRecord)` (frozen dataclass)
  - `class LLMProvider(Protocol)` (decorado con `@runtime_checkable`) con `async def decide(self, market_state: MarketState, memories: Sequence[TradingMemory], context: DecisionContext, prompt: Prompt) -> DecisionResult`
  - `class PromptStore(Protocol)` (decorado con `@runtime_checkable`) con `def load(self, kind: str, version: str) -> Prompt`
  - `class PromptNotFound(Exception)`

- [ ] **Step 1: Escribir el test que falla** — `tests/test_llm_ports.py`

```python
from application.ports.llm import DecisionResult, LLMProvider, PromptStore
from domain.llm.call import LLMCallRecord
from domain.llm.prompt import Prompt
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action


def _call() -> LLMCallRecord:
    return LLMCallRecord(
        provider="fake", requested_model="m", reported_model_version="m-v1",
        request="{}", response="{}", prompt_hash="h", market_state_hash="ms",
        temperature=0.0, parameters=(), timestamp_ms=0, latency_ms=1,
        input_tokens=0, output_tokens=0, cost_usd=0.0,
    )


def test_decision_result_carries_decision_and_call() -> None:
    d = TradingDecision(timestamp_ms=0, action=Action.HOLD, confidence=0.0)
    r = DecisionResult(decision=d, call=_call())
    assert r.decision is d
    assert r.call.input_tokens == 0


class FakeProvider:
    async def decide(self, market_state, memories, context, prompt) -> DecisionResult:
        raise NotImplementedError


class FakePromptStore:
    def load(self, kind: str, version: str) -> Prompt:
        raise NotImplementedError


def test_protocols_are_structurally_satisfied() -> None:
    # LLMProvider y PromptStore se declaran @runtime_checkable: isinstance() verifica
    # la forma estructural (presencia de los métodos del Protocol).
    assert isinstance(FakeProvider(), LLMProvider)
    assert isinstance(FakePromptStore(), PromptStore)
```

> **Nota de orden:** esta tarea referencia `domain.llm.call.LLMCallRecord` y `domain.llm.prompt.Prompt`, que se crean en la Task 3. Implementar Task 3 (dominio) antes de ejecutar los tests de esta tarea, o crear los dos módulos de dominio mínimos en esta tarea. Se recomienda ejecutar Tasks 1→3 y luego validar Task 2.

- [ ] **Step 2: Ejecutar para verificar fallo** — FAIL (imports faltantes).
- [ ] **Step 3: Implementar** `src/application/ports/llm.py`.
- [ ] **Step 4: Ejecutar para verificar paso** — `uv run pytest tests/test_llm_ports.py -v` → PASS.
- [ ] **Step 5: Staging + reporte** (commit diferido).

---

### Task 3: Dominio LLM — presupuesto, coste, llamada, prompt

**Files:**
- Create: `src/domain/llm/__init__.py` (vacío)
- Create: `src/domain/llm/budget.py`
- Create: `src/domain/llm/cost.py`
- Create: `src/domain/llm/call.py`
- Create: `src/domain/llm/prompt.py`
- Test: `tests/test_llm_budget.py`, `tests/test_llm_cost.py`, `tests/test_llm_prompt.py`

**Interfaces:**
- Consumes: stdlib (`enum`, `dataclasses`, `hashlib`).
- Produces:
  - `BudgetLevel(StrEnum)`: `OK`, `ALERT_50`, `ALERT_75`, `ALERT_90`, `BLOCKED`
  - `Budget(limit_usd: float, consumed_usd: float = 0.0)` con `ratio() -> float`, `level() -> BudgetLevel`, `is_blocked() -> bool`, `consume(cost_usd: float) -> Budget`
  - `BudgetState(experiment: Budget, monthly: Budget)` con `record(cost_usd) -> BudgetState`, `is_blocked() -> bool`
  - `max_level(a: BudgetLevel, b: BudgetLevel) -> BudgetLevel`
  - `compute_cost(input_tokens: int, output_tokens: int, price_input_mtok: float, price_output_mtok: float) -> float`
  - `LLMCallRecord(provider, requested_model, reported_model_version, request, response, prompt_hash, market_state_hash, temperature, parameters: tuple[tuple[str, str], ...], timestamp_ms, latency_ms, input_tokens, output_tokens, cost_usd, error: str = "")`
  - `Prompt(kind: str, version: str, text: str)` con property `hash -> str`
  - `prompt_hash(text: str) -> str`

- [ ] **Step 1: Escribir los tests que fallan** — `tests/test_llm_budget.py`

```python
from domain.llm.budget import Budget, BudgetLevel, BudgetState, max_level


def test_budget_levels_thresholds() -> None:
    assert Budget(100.0, 0.0).level() is BudgetLevel.OK
    assert Budget(100.0, 49.9).level() is BudgetLevel.OK
    assert Budget(100.0, 50.0).level() is BudgetLevel.ALERT_50
    assert Budget(100.0, 75.0).level() is BudgetLevel.ALERT_75
    assert Budget(100.0, 90.0).level() is BudgetLevel.ALERT_90
    assert Budget(100.0, 100.0).level() is BudgetLevel.BLOCKED
    assert Budget(100.0, 150.0).level() is BudgetLevel.BLOCKED


def test_budget_consume_is_immutable() -> None:
    b = Budget(100.0, 40.0)
    b2 = b.consume(20.0)
    assert b.consumed_usd == 40.0
    assert b2.consumed_usd == 60.0
    assert b2.level() is BudgetLevel.ALERT_50


def test_budget_zero_limit_never_blocks() -> None:
    assert Budget(0.0, 0.0).is_blocked() is False


def test_state_records_both_and_blocks() -> None:
    s = BudgetState(experiment=Budget(10.0), monthly=Budget(1000.0))
    s2 = s.record(6.0)
    assert s2.experiment.consumed_usd == 6.0
    assert s2.monthly.consumed_usd == 6.0
    assert s2.experiment.level() is BudgetLevel.ALERT_50
    assert s2.is_blocked() is False
    assert s2.record(4.0).experiment.is_blocked() is True
    assert s2.record(4.0).is_blocked() is True


def test_max_level_picks_more_severe() -> None:
    assert max_level(BudgetLevel.OK, BudgetLevel.ALERT_90) is BudgetLevel.ALERT_90
    assert max_level(BudgetLevel.BLOCKED, BudgetLevel.OK) is BudgetLevel.BLOCKED
```

- [ ] **Step 2:** Escribir `tests/test_llm_cost.py`

```python
from domain.llm.cost import compute_cost


def test_compute_cost_zero_tokens() -> None:
    assert compute_cost(0, 0, 0.27, 1.10) == 0.0


def test_compute_cost_per_million_tokens() -> None:
    assert compute_cost(1_000_000, 0, 0.27, 1.10) == 0.27
    assert compute_cost(0, 1_000_000, 0.27, 1.10) == 1.10
    assert compute_cost(500_000, 500_000, 0.27, 1.10) == 0.135 + 0.55
```

- [ ] **Step 3:** Escribir `tests/test_llm_prompt.py`

```python
from domain.llm.prompt import Prompt, prompt_hash


def test_prompt_hash_stable() -> None:
    assert prompt_hash("hola") == prompt_hash("hola")
    assert prompt_hash("hola") != prompt_hash("adios")


def test_prompt_hash_sha256_hex() -> None:
    h = prompt_hash("x")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_prompt_object_hash_matches_text() -> None:
    p = Prompt(kind="decision", version="v001", text="contenido")
    assert p.hash == prompt_hash("contenido")
```

- [ ] **Step 4: Ejecutar para verificar fallo** — `uv run pytest tests/test_llm_budget.py tests/test_llm_cost.py tests/test_llm_prompt.py -v` → FAIL.
- [ ] **Step 5: Implementar** los 4 módulos de dominio.
- [ ] **Step 6: Ejecutar para verificar paso** — `uv run pytest tests/test_llm_budget.py tests/test_llm_cost.py tests/test_llm_prompt.py tests/test_llm_ports.py -v` → PASS.
- [ ] **Step 7: Staging + reporte** (commit diferido).

---

### Task 4: Schemas Pydantic — validación estricta

**Files:**
- Create: `src/infrastructure/llm/schemas.py`
- Test: `tests/test_llm_schemas.py`

**Interfaces:**
- Consumes: `TradingDecision`, `Action`, `Intensity`.
- Produces:
  - `DecisionResponse(BaseModel)` con `decision: Literal["BUY","SELL","HOLD"]`, `confidence: float = Field(ge=0.0, le=1.0)`, `intensity: Literal["LOW","MEDIUM","HIGH"]`, `rationale_summary: str = ""`, `supporting_factors: list[str] = []`, `risk_factors: list[str] = []`, y `to_decision(timestamp_ms: int) -> TradingDecision`.
  - `DeepSeekChatResponse(BaseModel)` con `model: str = ""`, `choices: list[Choice]`, `usage: Usage` (`prompt_tokens`, `completion_tokens`).

- [ ] **Step 1: Escribir el test que falla** — `tests/test_llm_schemas.py`

```python
import pytest
from pydantic import ValidationError

from domain.trading.signal import Action, Intensity
from infrastructure.llm.schemas import DecisionResponse, DeepSeekChatResponse


def test_valid_decision_parses() -> None:
    d = DecisionResponse.model_validate({
        "decision": "BUY", "confidence": 0.73, "intensity": "MEDIUM",
        "rationale_summary": "momentum", "supporting_factors": ["MACD_BULLISH"],
        "risk_factors": ["BTC_WEAK"],
    })
    td = d.to_decision(timestamp_ms=7)
    assert td.action is Action.BUY
    assert td.intensity is Intensity.MEDIUM
    assert td.confidence == 0.73
    assert td.supporting_factors == ("MACD_BULLISH",)


@pytest.mark.parametrize("payload", [
    {"decision": "FOMO", "confidence": 0.5, "intensity": "MEDIUM"},
    {"decision": "BUY", "confidence": 1.5, "intensity": "MEDIUM"},
    {"decision": "BUY", "confidence": -0.1, "intensity": "MEDIUM"},
    {"decision": "BUY", "confidence": 0.5, "intensity": "EXTREME"},
    {"decision": "BUY", "intensity": "MEDIUM"},  # falta confidence
    {},
])
def test_invalid_decision_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        DecisionResponse.model_validate(payload)


def test_confidence_bounds_exact_edges_accepted() -> None:
    DecisionResponse.model_validate({"decision": "HOLD", "confidence": 0.0, "intensity": "LOW"})
    DecisionResponse.model_validate({"decision": "HOLD", "confidence": 1.0, "intensity": "HIGH"})


def test_deepseek_chat_response_parses() -> None:
    raw = {
        "model": "deepseek-v4-flash",
        "choices": [{"message": {"role": "assistant",
                                  "content": '{"decision":"HOLD","confidence":0.1,"intensity":"LOW"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    r = DeepSeekChatResponse.model_validate(raw)
    assert r.model == "deepseek-v4-flash"
    assert r.usage.prompt_tokens == 10
    assert r.choices[0].message.content.startswith("{")
```

- [ ] **Step 2: Ejecutar para verificar fallo** — FAIL.
- [ ] **Step 3: Implementar** `src/infrastructure/llm/schemas.py`.
- [ ] **Step 4: Ejecutar para verificar paso** — PASS.
- [ ] **Step 5: Staging + reporte** (commit diferido).

---

### Task 5: Versionado de prompts

**Files:**
- Create: `src/infrastructure/llm/prompts.py`
- Create: `prompts/decision/v001.md`
- Test: `tests/test_prompt_store.py`

**Interfaces:**
- Consumes: `Prompt`, `PromptStore`, `PromptNotFound`.
- Produces: `FilePromptStore(base_dir: str | Path = "prompts")` con `load(kind: str, version: str) -> Prompt`.

- [ ] **Step 1: Escribir el test que falla** — `tests/test_prompt_store.py`

```python
import pytest

from application.ports.llm import PromptNotFound
from infrastructure.llm.prompts import FilePromptStore


def test_load_prompt_by_kind_and_version(tmp_path) -> None:
    (tmp_path / "decision").mkdir()
    (tmp_path / "decision" / "v001.md").write_text("eres un agente de trading", encoding="utf-8")
    store = FilePromptStore(base_dir=tmp_path)
    p = store.load("decision", "v001")
    assert p.kind == "decision"
    assert p.version == "v001"
    assert p.text == "eres un agente de trading"
    assert len(p.hash) == 64


def test_load_missing_prompt_raises(tmp_path) -> None:
    store = FilePromptStore(base_dir=tmp_path)
    with pytest.raises(PromptNotFound):
        store.load("decision", "v999")
```

- [ ] **Step 2:** Escribir `prompts/decision/v001.md` (prompt del sistema; pide JSON estricto con `decision`/`confidence`/`intensity`/`rationale_summary`/`supporting_factors`/`risk_factors`, sin montos monetarios, long-only ETH/USDT spot).
- [ ] **Step 3: Ejecutar para verificar fallo** — `uv run pytest tests/test_prompt_store.py -v` → FAIL.
- [ ] **Step 4: Implementar** `FilePromptStore`.
- [ ] **Step 5: Ejecutar para verificar paso** — PASS (verifica que `prompts/decision/v001.md` es legible vía `FilePromptStore()` sin base_dir).
- [ ] **Step 6: Staging + reporte** (commit diferido).

---

### Task 6: Adapter DeepSeek

**Files:**
- Create: `src/infrastructure/llm/deepseek.py`
- Test: `tests/test_deepseek.py`

**Interfaces:**
- Consumes: `LLMProvider`, `DecisionResult`, `Prompt`, `DeepSeekChatResponse`, `DecisionResponse`, `compute_cost`, `LLMCallRecord`, `TradingDecision`.
- Produces:
  - `DeepSeekConfig(api_key: str, model: str = "deepseek-v4-flash", base_url: str = "https://api.deepseek.com", timeout: float = 30.0, temperature: float = 0.0, price_input_mtok: float = 0.27, price_output_mtok: float = 1.10, max_retries: int = 2)` (frozen)
  - `render_decision_messages(prompt: Prompt, market_state: MarketState, memories: Sequence[TradingMemory]) -> list[dict[str, str]]` (puro)
  - `DeepSeekProvider` que implementa `LLMProvider.decide` (async) devolviendo `DecisionResult`.

- [ ] **Step 1: Escribir el test que falla** — `tests/test_deepseek.py` (usa `httpx.MockTransport`)

```python
import json

import httpx
import pytest

from domain.market.state import MarketState
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action
from infrastructure.llm.deepseek import DeepSeekConfig, DeepSeekProvider


def _config(handler) -> tuple[DeepSeekProvider, DeepSeekConfig]:
    cfg = DeepSeekConfig(api_key="test-key")
    provider = DeepSeekProvider(cfg, transport=httpx.MockTransport(handler))
    return provider, cfg


def _state() -> MarketState:
    return MarketState(symbol="ETHUSDT", timestamp_ms=1000, health="healthy",
                       regime=None, timeframes={}, orderbook=None, btc=None)


def _json_response(content: str, model: str = "deepseek-v4-flash",
                   pt: int = 10, ct: int = 5) -> httpx.Response:
    return httpx.Response(200, json={"model": model, "choices": [
        {"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct}})


async def test_valid_decision(tmp_path) -> None:
    content = '{"decision":"BUY","confidence":0.7,"intensity":"HIGH","rationale_summary":"m"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(content)

    provider, _ = _config(handler)
    prompt = type("P", (), {"text": "sistema", "hash": "h"})()
    result = await provider.decide(_state(), [], type("C", (), {
        "symbol": "ETHUSDT", "timestamp_ms": 1000, "experiment_id": "",
        "prompt_version": "v001", "market_state_hash": "ms"})() , prompt)
    assert result.decision.action is Action.BUY
    assert result.decision.is_fallback is False
    assert result.call.provider == "deepseek"
    assert result.call.reported_model_version == "deepseek-v4-flash"
    assert result.call.cost_usd > 0.0


async def test_invalid_json_falls_back_to_hold(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response("esto no es json")

    provider, _ = _config(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.action is Action.HOLD
    assert result.decision.is_fallback is True
    assert result.decision.fallback_reason is not None


async def test_schema_invalid_falls_back_to_hold(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response('{"decision":"BUY","confidence":9.9,"intensity":"HIGH"}')

    provider, _ = _config(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.is_fallback is True


async def test_http_error_falls_back_to_hold(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider, _ = _config(handler)
    result = await provider.decide(_state(), [], _ctx(), _prompt())
    assert result.decision.is_fallback is True
    assert result.call.error != ""


def _ctx():
    return type("C", (), {"symbol": "ETHUSDT", "timestamp_ms": 1000,
                          "experiment_id": "", "prompt_version": "v001",
                          "market_state_hash": "ms"})()


def _prompt():
    return type("P", (), {"text": "sistema", "hash": "h"})()
```

> **Nota:** en el test real importar `DecisionContext`, `Prompt` desde el dominio en lugar de `type(...)`. Simplificar helpers si es necesario.

- [ ] **Step 2: Ejecutar para verificar fallo** — FAIL.
- [ ] **Step 3: Implementar** `deepseek.py` (construcción de mensajes, POST `/chat/completions`, parseo, coste, `LLMCallRecord`, retries limitados; nunca lanza en fallos esperados).
- [ ] **Step 4: Ejecutar para verificar paso** — PASS.
- [ ] **Step 5: Staging + reporte** (commit diferido).

---

### Task 7: CostMonitor + DecisionAgent (fail-safe + presupuesto)

**Files:**
- Create: `src/application/services/cost_monitor.py`
- Create: `src/application/services/decision_agent.py`
- Test: `tests/test_decision_agent.py`

**Interfaces:**
- Consumes: `Budget`, `BudgetState`, `BudgetLevel`, `max_level`, `LLMCallRecord`, `LLMProvider`, `PromptStore`, `PromptNotFound`, `DecisionResult`, `TradingDecision`.
- Produces:
  - `CostMonitor(experiment_budget_usd: float, monthly_budget_usd: float)` con `record(call: LLMCallRecord) -> BudgetLevel`, `is_blocked() -> bool`, `total_cost_usd -> float`, `state -> BudgetState`.
  - `DecisionAgentConfig(prompt_kind: str = "decision", default_prompt_version: str = "v001")` (frozen)
  - `DecisionAgent(provider: LLMProvider, prompt_store: PromptStore, cost_monitor: CostMonitor, config: DecisionAgentConfig | None = None)` con `async def decide(self, market_state, memories, context) -> TradingDecision`.

- [ ] **Step 1: Escribir el test que falla** — `tests/test_decision_agent.py` (usa fake provider)

```python
import pytest

from application.ports.llm import DecisionResult, PromptNotFound
from application.services.cost_monitor import CostMonitor
from application.services.decision_agent import DecisionAgent, DecisionAgentConfig
from domain.llm.call import LLMCallRecord
from domain.trading.decision import TradingDecision
from domain.trading.signal import Action, Intensity


def _call(cost: float = 1.0, error: str = "") -> LLMCallRecord:
    return LLMCallRecord(provider="fake", requested_model="m", reported_model_version="v",
                         request="{}", response="{}", prompt_hash="h", market_state_hash="ms",
                         temperature=0.0, parameters=(), timestamp_ms=0, latency_ms=1,
                         input_tokens=100, output_tokens=100, cost_usd=cost, error=error)


class FakeProvider:
    def __init__(self, result: DecisionResult | None = None, exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.called = False

    async def decide(self, market_state, memories, context, prompt) -> DecisionResult:
        self.called = True
        if self.exc:
            raise self.exc
        assert self.result is not None
        return self.result


class FakePromptStore:
    def load(self, kind: str, version: str):
        return type("P", (), {"kind": kind, "version": version, "text": "t", "hash": "h"})()


def _ctx():
    return type("C", (), {"symbol": "ETHUSDT", "timestamp_ms": 1000,
                          "experiment_id": "", "prompt_version": "", "market_state_hash": ""})()


async def test_decision_recorded_and_returned() -> None:
    d = TradingDecision(timestamp_ms=1000, action=Action.BUY, confidence=0.7)
    provider = FakeProvider(result=DecisionResult(d, _call(cost=2.0)))
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(provider, FakePromptStore(), monitor)
    out = await agent.decide(None, [], _ctx())
    assert out is d
    assert monitor.total_cost_usd == 2.0
    assert provider.called is True


async def test_budget_blocked_returns_hold_without_calling() -> None:
    d = TradingDecision(timestamp_ms=1000, action=Action.BUY, confidence=0.7)
    provider = FakeProvider(result=DecisionResult(d, _call(cost=0.0)))
    monitor = CostMonitor(experiment_budget_usd=1.0, monthly_budget_usd=100.0)
    monitor.record(_call(cost=1.0))  # agota experiment budget
    agent = DecisionAgent(provider, FakePromptStore(), monitor)
    out = await agent.decide(None, [], _ctx())
    assert out.is_fallback is True
    assert out.fallback_reason == "budget_exhausted"
    assert provider.called is False


async def test_provider_exception_returns_hold() -> None:
    provider = FakeProvider(exc=RuntimeError("boom"))
    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(provider, FakePromptStore(), monitor)
    out = await agent.decide(None, [], _ctx())
    assert out.is_fallback is True
    assert "RuntimeError" in (out.fallback_reason or "")


async def test_prompt_not_found_returns_hold() -> None:
    class Missing:
        def load(self, kind, version):
            raise PromptNotFound("x")

    monitor = CostMonitor(experiment_budget_usd=10.0, monthly_budget_usd=100.0)
    agent = DecisionAgent(FakeProvider(), Missing(), monitor)
    out = await agent.decide(None, [], _ctx())
    assert out.is_fallback is True
    assert out.fallback_reason == "prompt_not_found"
```

- [ ] **Step 2: Ejecutar para verificar fallo** — FAIL.
- [ ] **Step 3: Implementar** `cost_monitor.py` y `decision_agent.py`.
- [ ] **Step 4: Ejecutar para verificar paso** — PASS.
- [ ] **Step 5: Staging + reporte** (commit diferido).

---

### Task 8: Versionado de experimentos

**Files:**
- Modify: `src/domain/experiments/experiment.py`
- Modify: `tests/test_experiment.py`

**Interfaces:**
- Consumes: `ExperimentMetadata` (existente).
- Produces: campos nuevos en `ExperimentMetadata`: `prompt_version: str = ""`, `llm_provider: str = ""`, `llm_model: str = ""`, `embedding_provider: str = ""`, `embedding_model: str = ""`, `risk_config_version: str = ""`. Todos entran en `_identity_fields`.

- [ ] **Step 1: Escribir el test que falla** (añadir a `tests/test_experiment.py`):

```python
def test_llm_fields_affect_id() -> None:
    base = build_experiment_id(_meta())
    assert build_experiment_id(_meta(prompt_version="v002")) != base
    assert build_experiment_id(_meta(llm_provider="openai")) != base
    assert build_experiment_id(_meta(llm_model="deepseek-v4-pro")) != base


def test_new_fields_default_to_empty() -> None:
    m = _meta()
    assert m.prompt_version == ""
    assert m.llm_provider == ""
    assert m.risk_config_version == ""
```

- [ ] **Step 2: Ejecutar para verificar fallo** — FAIL (AttributeError / constructor).
- [ ] **Step 3: Implementar** campos nuevos + `_identity_fields`.
- [ ] **Step 4: Ejecutar para verificar paso** — `uv run pytest tests/test_experiment.py -v` → PASS.
- [ ] **Step 5: Staging + reporte** (commit diferido).

---

### Task 9: Configuración, wiring y verificación completa

**Files:**
- Modify: `src/settings.py`
- Modify: `config/base.yaml`
- Modify: `.env.example` (comentar claves de presupuesto/modelo; SIN secretos)

**Interfaces:**
- Consumes: `Settings` (existente).
- Produces: campos nuevos en `Settings`: `llm_provider: str = "deepseek"`, `llm_model: str = "deepseek-v4-flash"`, `llm_base_url: str = "https://api.deepseek.com"`, `llm_api_key: SecretStr = SecretStr("")`, `llm_timeout: float = 30.0`, `llm_temperature: float = 0.0`, `llm_price_input_mtok: float = 0.27`, `llm_price_output_mtok: float = 1.10`, `llm_experiment_budget_usd: float = 5.0`, `llm_monthly_budget_usd: float = 50.0`, `prompts_dir: str = "prompts"`.

- [ ] **Step 1: Escribir test** (añadir a `tests/test_settings.py`, convención existente: `load_settings()` + `monkeypatch`):

```python
from settings import Settings


def test_llm_settings_defaults(monkeypatch: MonkeyPatch) -> None:
    for var in ("LLM_MODEL", "LLM_PROVIDER", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    s = load_settings()
    assert s.llm_provider == "deepseek"
    assert s.llm_model == "deepseek-v4-flash"
    assert s.llm_api_key.get_secret_value() == ""


def test_llm_settings_from_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("LLM_EXPERIMENT_BUDGET_USD", "7.5")
    s = load_settings()
    assert s.llm_model == "deepseek-v4-pro"
    assert s.llm_experiment_budget_usd == 7.5
```

- [ ] **Step 2: Ejecutar para verificar fallo** — FAIL.
- [ ] **Step 3: Implementar** settings + yaml.
- [ ] **Step 4: Ejecutar para verificar paso** — PASS.
- [ ] **Step 5: Verificación completa**:
  - `uv run pytest --cov=src --cov-branch --cov-fail-under=90`
  - `uv run ruff check . && uv run ruff format --check .`
  - `uv run mypy src tests`
- [ ] **Step 6: Evidencia** — `harness/scripts/evidence.sh` para cada comando relevante.
- [ ] **Step 7: Staging + Commit Candidate Report** (flujo-commits, sin commit sin autorización).

---

## Self-Review

**1. Spec coverage (PRD §17–20, §37–39, §60 + 9 entregables del ledger):**
- `LLMProvider` (Protocol) → Task 2. ✅
- DeepSeek adapter → Task 6. ✅
- structured output (contrato JSON §19) → Task 1 (dominio) + Task 4 (schemas). ✅
- Pydantic validation → Task 4. ✅
- cost monitoring → Task 3 (`compute_cost`, `LLMCallRecord`) + Task 7 (`CostMonitor`). ✅
- budget (experiment/monthly, alerts 50/75/90, block 100) → Task 3 (dominio) + Task 7 (enforcement). ✅
- fallback HOLD (§20) → Task 6 (adapter) + Task 7 (service). ✅
- prompt versioning (§37) → Task 5. ✅
- experiment versioning (§38–39) → Task 8. ✅
- Reproducibilidad §38 (provider, requested_model, reported_model_version, request, response, prompt_hash, market_state_hash, temperature, parameters, timestamp, latency, tokens, cost) → `LLMCallRecord` Task 3 + relleno en Task 6. ✅

**2. Placeholder scan:** sin TBD/TODO; cada tarea tiene código de test e implementación concreta.

**3. Type consistency:** `TradingDecision`, `DecisionContext`, `TradingMemory`, `LLMCallRecord`, `Prompt`, `DecisionResult`, `Budget`, `BudgetState`, `BudgetLevel`, `CostMonitor`, `DecisionAgent`, `DeepSeekProvider`, `FilePromptStore` usados con nombres consistentes en todas las tareas. `Action`/`Intensity` importados de `domain.trading.signal`. `PromptNotFound` definido en `application.ports.llm` y consumido en `decision_agent.py` y `prompts.py`.

## Execution Handoff

Tras guardar el plan, ofrecer: (1) Subagent-Driven (recomendado) o (2) Inline Execution.
