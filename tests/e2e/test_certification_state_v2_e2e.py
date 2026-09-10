"""E2E productor → JSON → evaluador (16c.6 / Task 8) — el MISMO productor desplegado.

Garantía clave: el JSON v2 de certificación que evalúa
``harness/scripts/paper_certification.py`` sale EXCLUSIVAMENTE de
``build_certification_state_v2`` + ``write_certification_state_v2`` (el productor
real del paper-runner). NINGÚN caso construye ``frozen``/``current``/``operational``
a mano (regla anti-manual del brief).

Cobertura (8 casos obligatorios):

1. RUNNING + 30d + 30 heartbeats + evidencia completa ⇒ PASS (age >= 30).
2. 29d de reloj ⇒ FAIL (calendar_days).
3. 30d de reloj pero 29 heartbeats ⇒ FAIL (metrics_history_days).
4. Corrupción contable compensada (fee↑ price↓, equity final bit-igual) tras
   avanzar el libro ⇒ accounting FAIL + evaluador FAIL con la razón contable.
5. Safeguard evidence con risk_config_version distinta ⇒ kill_switch/daily_loss
   FAIL ⇒ evaluador FAIL.
6. Drift de strategy_version (misma sesión, día 30) ⇒ frozen preservado byte a
   byte, RUNNING intacto, `frozen_versions` FAIL, sin re-ancla.
7. Estado NOT_STARTED evaluado a cualquier edad ⇒ FAIL (calendar_days), jamás PASS.
8. JSON estricto: json.dumps(estado, allow_nan=False) OK y sin NaN/Infinity.
9. Fills legítimos a mitad de corrida entre escrituras (Task 8c F2): posición
   abierta que cruza writes + cierres reales los días 5/17 ⇒ PASS en cada
   escritura (reconciliación three-way con checkpoint por cursor) y el libro
   avanza — el punto F2 que el libro estático de Task 4b no podía reconciliar.

Los escenarios se siembran con repos in-memory + motor real (PaperEngine /
Portfolio) para producir fills y equity bit-exactos (reconciliación residual == 0
exacto). Evaluador real importado por ruta. Sin red, sin LLM.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from application.ports.paper_trading import PaperTradeEvent
from application.services.accounting_reconciliation import (
    MissingMarkError,
    latest_persisted_mark,
    reconcile_with_book,
)
from application.services.certification_snapshot import (
    RuntimeArtifact,
    build_certification_state_v2,
    certification_phase,
    runtime_artifact,
    start_certification,
    write_certification_state_v2,
)
from application.services.paper_engine import PaperEngine
from application.services.paper_runner import PaperRunSummary, summarize_events
from domain.market.candle import Candle
from domain.portfolio.portfolio import Portfolio
from domain.risk.config import RiskConfig
from domain.trading.decision import TradingDecision
from domain.trading.fill import Fill
from domain.trading.signal import Action, Intensity

SYMBOL = "ETHUSDT"
TIMEFRAME = "15m"
INTERVAL_MS = 900_000
DAY_MS = 86_400_000
CERT_DAYS = 30
SLOTS_PER_DAY = 96

APP_VERSION = "0.2.0"
GIT_COMMIT = "a" * 7
DIGEST = "sha256:ff"
STRATEGY_VERSION = "baseline-v1"
RISK_VERSION = "risk-v1"

# Día UTC 2026-09-01T00:00:00Z (ancla t0 determinista).
T0 = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)
MARKET_CLOSE = 100.0

_KILL_SWITCH_STEPS = [
    "activate",
    "buy_rejected",
    "persist",
    "restart_still_active",
    "buy_still_rejected",
    "operator_reset",
]
_DAILY_LOSS_STEPS = [
    "daily_loss_exceeded",
    "buy_rejected",
    "sell_allowed",
    "restart_persists",
    "utc_rollover_reset",
]

_T = Any


def _load_evaluator() -> Any:
    """Carga el evaluador real del harness por ruta (importlib, sin import src)."""
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "harness" / "scripts" / "paper_certification.py"
    spec = importlib.util.spec_from_file_location("paper_certification_e2e_eval", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _utc_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _report_path(now_ms: int) -> str:
    stamp = datetime.fromtimestamp(now_ms / 1000, tz=UTC).strftime("%Y%m%d-%H%M%S")
    return f"/tmp/paper-e2e-reports/paper-{stamp}.md"


def _candle(ts_ms: int, close: float) -> Candle:
    return Candle(ts_ms, close - 1.0, close + 1.0, close - 2.0, close, 1.0, close)


def _decision(action: Action, ts: int) -> TradingDecision:
    return TradingDecision(
        timestamp_ms=ts, action=action, confidence=0.8, intensity=Intensity.MEDIUM
    )


def _event_from_engine(
    engine: PaperEngine,
    *,
    ts: int,
    action: Action,
    session_id: str,
    price: float = MARKET_CLOSE,
    atr: float = 40.0,
) -> PaperTradeEvent:
    """Replica paper_runner._process: engine.on_price + equity mark_to_market."""
    paper_event = engine.on_price(
        decision=_decision(action, ts), price=price, atr=atr, timestamp_ms=ts
    )
    equity = engine.mark_to_market(price=price)
    fill = paper_event.fill
    return PaperTradeEvent(
        session_id=session_id,
        strategy_version=STRATEGY_VERSION,
        strategy_hash="h" * 64,
        decision_source="baseline",
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        timestamp_ms=ts,
        action=paper_event.action.name,
        filled=paper_event.filled,
        risk_reason=paper_event.risk_reason,
        exit_reason=paper_event.exit_reason,
        exec_price=fill.exec_price if fill is not None else None,
        quantity=fill.quantity if fill is not None else None,
        fee=fill.fee if fill is not None else 0.0,
        slippage_cost=fill.slippage_cost if fill is not None else 0.0,
        equity=equity,
        kill_switch_active=False,
        decision_context={"schema_version": 1, "signal_reason": "e2e"},
    )


def _flat_scenario_events(
    session_id: str,
) -> tuple[list[PaperTradeEvent], list[Candle], RiskConfig]:
    """Sesión 30d: round-trip BUY/SELL real el día 0 + un evento HOLD por día.

    Los fills (BUY y SELL full close) salen del PaperEngine real; la equity de cada
    evento es ``mark_to_market(close)`` del engine. Velas continuas 15m sobre todo
    el rango (sin huecos). El día 0 queda flat, así que la reconciliación espejo da
    residual exacto 0 en CADA escritura diaria.
    """
    config = RiskConfig()
    engine = PaperEngine(config=config)
    ordered: list[tuple[int, Action]] = []
    for day in range(CERT_DAYS):
        base = T0 + day * DAY_MS
        if day == 0:
            ordered.append((base + 2 * INTERVAL_MS, Action.BUY))
            ordered.append((base + 40 * INTERVAL_MS, Action.HOLD))
            ordered.append((base + 80 * INTERVAL_MS, Action.SELL))
        else:
            ordered.append((base + 40 * INTERVAL_MS, Action.HOLD))
    ordered.sort(key=lambda item: item[0])
    events = [
        _event_from_engine(engine, ts=ts, action=action, session_id=session_id)
        for ts, action in ordered
    ]
    candles = [
        _candle(T0 + i * INTERVAL_MS, MARKET_CLOSE) for i in range(CERT_DAYS * SLOTS_PER_DAY)
    ]
    return events, candles, config


def _open_position_events(
    session_id: str, corrupt: bool = False
) -> tuple[list[PaperTradeEvent], list[Candle], RiskConfig]:
    """Sesión con posición ABIERTA real (Portfolio.apply_buy) para el caso 4.

    Libro bueno autoritativo: Portfolio real tras ``BUY 1.0 @ exec 100.0 fee 0.1``
    (capital 100_000), con mark constante 110.0 en todas las velas (equity estable
    ⇒ la reconciliación diaria avanza PASS mientras no haya corrupción).

    ``corrupt=True`` devuelve el MISMO evento BUY pero con ``fee↑`` (0.1 → 5.1) y
    ``price↓`` (exec 100.0 → 80.0, qty 1.0 → 0.5): la equity final reconstruida
    (99954.9 + 0.5*110 = 100009.9) es bit-igual a la del libro bueno, pero
    cash/position/avg/fees difieren ⇒ la comparación componente a componente FAIL.
    """
    capital = 100_000.0
    mark = 110.0
    config = replace(RiskConfig(), capital=capital)
    ts_buy = T0
    if corrupt:
        exec_price = 80.0
        quantity = 0.5
        fee = 5.1
    else:
        exec_price = 100.0
        quantity = 1.0
        fee = 0.1
    pf = Portfolio(initial_cash=capital, cash=capital)
    pf.apply_buy(
        Fill(ts_buy, Action.BUY, exec_price, exec_price, quantity, quantity * exec_price, fee, 0.0)
    )
    events: list[PaperTradeEvent] = [
        PaperTradeEvent(
            session_id=session_id,
            strategy_version=STRATEGY_VERSION,
            strategy_hash="h" * 64,
            decision_source="baseline",
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            timestamp_ms=ts_buy,
            action="BUY",
            filled=True,
            risk_reason="",
            exit_reason="",
            exec_price=exec_price,
            quantity=quantity,
            fee=fee,
            slippage_cost=0.0,
            equity=pf.equity(mark),
            kill_switch_active=False,
            decision_context={"schema_version": 1, "signal_reason": "e2e"},
        )
    ]
    for day in range(CERT_DAYS):
        events.append(
            PaperTradeEvent(
                session_id=session_id,
                strategy_version=STRATEGY_VERSION,
                strategy_hash="h" * 64,
                decision_source="baseline",
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                timestamp_ms=T0 + day * DAY_MS + 40 * INTERVAL_MS,
                action="HOLD",
                filled=False,
                risk_reason="",
                exit_reason="",
                exec_price=None,
                quantity=None,
                fee=0.0,
                slippage_cost=0.0,
                equity=pf.equity(mark),
                kill_switch_active=False,
                decision_context={"schema_version": 1, "signal_reason": "e2e"},
            )
        )
    events.sort(key=lambda event: event.timestamp_ms)
    candles = [_candle(T0 + i * INTERVAL_MS, mark) for i in range(CERT_DAYS * SLOTS_PER_DAY)]
    return events, candles, config


def _mid_run_fill_events(
    session_id: str,
) -> tuple[list[PaperTradeEvent], list[Candle], RiskConfig]:
    """Sesión 30d con FILLS LEGÍTIMOS a mitad de corrida (16c.6 / Task 8c F2).

    BUY 1.0 el día 0 (posición abierta que cruza varias escrituras), SELL de cierre
    el día 5, BUY 2.0 el día 12 y SELL de cierre el día 17 — todos con la aritmética
    REAL del Portfolio. La reconciliación three-way debe dar PASS en CADA escritura
    diaria (el incremental reanuda el checkpoint con ``entry_fees`` y rejuega los
    fills nuevos por cursor) y el libro debe avanzar: es el punto F2 que el libro
    estático de Task 4b no podía reconciliar (los componentes legítimos cambian
    entre writes sin que haya corrupción).
    """
    capital = 100_000.0
    mark = 110.0
    config = replace(RiskConfig(), capital=capital)
    pf = Portfolio(initial_cash=capital, cash=capital)

    fills: dict[int, tuple[Action, float, float, float]] = {}
    fills[T0 + 2 * INTERVAL_MS] = (Action.BUY, 100.0, 1.0, 0.1)
    fills[T0 + 5 * DAY_MS + 80 * INTERVAL_MS] = (Action.SELL, 120.0, 1.0, 0.2)
    fills[T0 + 12 * DAY_MS + 2 * INTERVAL_MS] = (Action.BUY, 95.0, 2.0, 0.15)
    fills[T0 + 17 * DAY_MS + 80 * INTERVAL_MS] = (Action.SELL, 110.0, 2.0, 0.3)

    events: list[PaperTradeEvent] = []
    scheduled: list[tuple[int, Action | None]] = []
    for day in range(CERT_DAYS):
        scheduled.append((T0 + day * DAY_MS + 40 * INTERVAL_MS, None))  # HOLD diario
        for ts in (
            T0 + day * DAY_MS + 2 * INTERVAL_MS,
            T0 + day * DAY_MS + 80 * INTERVAL_MS,
        ):
            if ts in fills:
                scheduled.append((ts, fills[ts][0]))
    scheduled.sort(key=lambda item: item[0])
    for ts, action in scheduled:
        if action is None:
            events.append(
                PaperTradeEvent(
                    session_id=session_id,
                    strategy_version=STRATEGY_VERSION,
                    strategy_hash="h" * 64,
                    decision_source="baseline",
                    symbol=SYMBOL,
                    timeframe=TIMEFRAME,
                    timestamp_ms=ts,
                    action="HOLD",
                    filled=False,
                    risk_reason="",
                    exit_reason="",
                    exec_price=None,
                    quantity=None,
                    fee=0.0,
                    slippage_cost=0.0,
                    equity=pf.equity(mark),
                    kill_switch_active=False,
                    decision_context={"schema_version": 1, "signal_reason": "e2e"},
                )
            )
            continue
        _action, exec_price, quantity, fee = fills[ts]
        pf.apply_buy(
            Fill(ts, _action, exec_price, exec_price, quantity, quantity * exec_price, fee, 0.0)
        ) if _action == Action.BUY else pf.apply_sell(
            Fill(ts, _action, exec_price, exec_price, quantity, quantity * exec_price, fee, 0.0)
        )
        events.append(
            PaperTradeEvent(
                session_id=session_id,
                strategy_version=STRATEGY_VERSION,
                strategy_hash="h" * 64,
                decision_source="baseline",
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                timestamp_ms=ts,
                action=_action.name,
                filled=True,
                risk_reason="",
                exit_reason="",
                exec_price=exec_price,
                quantity=quantity,
                fee=fee,
                slippage_cost=0.0,
                equity=pf.equity(mark),
                kill_switch_active=False,
                decision_context={"schema_version": 1, "signal_reason": "e2e"},
            )
        )
    candles = [_candle(T0 + i * INTERVAL_MS, mark) for i in range(CERT_DAYS * SLOTS_PER_DAY)]
    return events, candles, config


@dataclass(frozen=True, slots=True)
class Scenario:
    """Escenario sembrado (eventos + velas + config) listo para el recorrido diario."""

    events: list[PaperTradeEvent]
    candles: list[Candle]
    config: RiskConfig
    session_id: str

    def summary(self, now_ms: int) -> PaperRunSummary:
        scoped = [event for event in self.events if event.timestamp_ms <= now_ms]
        return summarize_events(
            sorted(scoped, key=lambda event: event.timestamp_ms), initial_equity=self.config.capital
        )

    def artifact(self, now_ms: int, *, strategy_version: str = STRATEGY_VERSION) -> RuntimeArtifact:
        summary = self.summary(now_ms)
        return runtime_artifact(
            summary=replace(summary, strategy_version=strategy_version),
            app_version=APP_VERSION,
            git_commit=GIT_COMMIT,
            docker_image_digest=DIGEST,
            risk_config=self.config,
            now_ms=now_ms,
        )

    def safeguard(self, *, risk_config_version: str = RISK_VERSION) -> dict[str, Any]:
        artifact_block = {
            "git_commit": GIT_COMMIT,
            "application_version": APP_VERSION,
            "docker_image_digest": DIGEST,
            "strategy_version": STRATEGY_VERSION,
            "risk_config_version": risk_config_version,
        }
        return {
            "kill_switch": {
                "type": "kill_switch",
                "status": "PASS",
                "at_iso": "2026-09-01T00:00:00Z",
                "steps": list(_KILL_SWITCH_STEPS),
                "artifact": dict(artifact_block),
            },
            "daily_loss": {
                "type": "daily_loss",
                "status": "PASS",
                "at_iso": "2026-09-01T00:00:00Z",
                "steps": list(_DAILY_LOSS_STEPS),
                "artifact": dict(artifact_block),
            },
        }


def _build_state(
    previous: dict[str, Any],
    scenario: Scenario,
    *,
    now_ms: int,
    events: list[PaperTradeEvent] | None = None,
    candles: list[Candle] | None = None,
    artifact: RuntimeArtifact | None = None,
    safeguard: dict[str, Any] | None = None,
    heartbeat_ok: bool = True,
    reconciliation_error: str | None = None,
    report_path: str | None = None,
) -> dict[str, Any]:
    """Compone el estado v2 con el PRODUCTOR REAL (sin construir JSON a mano)."""
    events_scoped = [
        e for e in (events if events is not None else scenario.events) if e.timestamp_ms <= now_ms
    ]
    candles_scoped = [
        c
        for c in (candles if candles is not None else scenario.candles)
        if c.timestamp_ms <= now_ms
    ]
    summary = summarize_events(
        sorted(events_scoped, key=lambda e: e.timestamp_ms), initial_equity=scenario.config.capital
    )
    used_artifact = artifact if artifact is not None else scenario.artifact(now_ms)
    if reconciliation_error is None:
        try:
            reconciliation = reconcile_with_book(
                events_scoped,
                initial_capital=scenario.config.capital,
                mark_price=latest_persisted_mark(candles_scoped),
                previous_book=previous.get("accounting_book"),
                interval_ms=INTERVAL_MS,
            )
        except MissingMarkError:
            reconciliation = None
            reconciliation_error = "missing_persisted_mark"
    else:
        reconciliation = None
    return build_certification_state_v2(
        previous=previous,
        summary=summary,
        events=events_scoped,
        candles=candles_scoped,
        heartbeat_ok=heartbeat_ok,
        today=_utc_date(now_ms),
        safeguard_evidence=safeguard if safeguard is not None else scenario.safeguard(),
        reconciliation=reconciliation,
        reconciliation_error=reconciliation_error,
        artifact=used_artifact,
        now_ms=now_ms,
        interval_ms=INTERVAL_MS,
        report_path=report_path if report_path is not None else _report_path(now_ms),
    )


def _write_state(state: dict[str, Any], state_path: Path) -> dict[str, Any]:
    write_certification_state_v2(state, state_path)
    with state_path.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    assert isinstance(loaded, dict)
    return loaded


def _progression(
    scenario: Scenario,
    state_path: Path,
    *,
    drop_heartbeat_day: int | None = None,
    events: list[PaperTradeEvent] | None = None,
    artifacts: dict[int, RuntimeArtifact] | None = None,
    safeguards: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recorrido diario real (día 0..29): escribe el estado v2 a disco cada día.

    Día 0: escritura periódica SIN ``start_certification`` ⇒ NOT_STARTED; luego
    ``start_certification`` en t0 (ancla) y escritura. Días 1..29: build + write
    (heartbeat diario, reconciliación con el libro, safeguards).
    """
    previous: dict[str, Any] = {}
    # Día 0 — escritura periódica antes de START (clock NOT_STARTED, sin ancla).
    day0_now = T0 + DAY_MS
    state = _build_state(
        previous,
        scenario,
        now_ms=day0_now,
        events=events,
        artifact=artifacts.get(0) if artifacts else None,
        safeguard=safeguards.get(0) if safeguards else None,
        heartbeat_ok=True,
    )
    assert certification_phase(state) == "NOT_STARTED"
    previous = _write_state(state, state_path)

    # START explícito del operador en t0 (ancla única).
    artifact0 = artifacts.get(0) if artifacts else None
    anchored = start_certification(
        previous,
        artifact0 if artifact0 is not None else scenario.artifact(day0_now),
        now_ms=T0,
    )
    previous = _write_state(anchored, state_path)
    assert certification_phase(previous) == "RUNNING"

    for day in range(1, CERT_DAYS):
        now = T0 + (day + 1) * DAY_MS
        heartbeat_ok = not (drop_heartbeat_day is not None and day == drop_heartbeat_day)
        state = _build_state(
            previous,
            scenario,
            now_ms=now,
            events=events,
            artifact=artifacts.get(day) if artifacts else None,
            safeguard=safeguards.get(day) if safeguards else None,
            heartbeat_ok=heartbeat_ok,
        )
        previous = _write_state(state, state_path)
    return previous


def _assert_strict_json(state: dict[str, Any]) -> None:
    """json.dumps con allow_nan=False no lanza y el dump no contiene NaN/Infinity."""
    dumped = json.dumps(state, allow_nan=False)
    for token in ("NaN", "Infinity", "-Infinity"):
        assert token not in dumped


def _evaluate(state: dict[str, Any], *, at_ms: int) -> Any:
    evaluator = _load_evaluator()
    return evaluator.evaluate_certification(state, evaluated_at=at_ms)


def _check(report: Any, name: str) -> Any:
    return next(check for check in report.checks if check.name == name)


@pytest.fixture(scope="module")
def flat_scenario() -> Scenario:
    events, candles, config = _flat_scenario_events("e2e-flat")
    return Scenario(events=events, candles=candles, config=config, session_id="e2e-flat")


@pytest.fixture(scope="module")
def open_scenario() -> Scenario:
    events, candles, config = _open_position_events("e2e-open", corrupt=False)
    return Scenario(events=events, candles=candles, config=config, session_id="e2e-open")


@pytest.fixture(scope="module")
def mid_run_scenario() -> Scenario:
    events, candles, config = _mid_run_fill_events("e2e-midrun")
    return Scenario(events=events, candles=candles, config=config, session_id="e2e-midrun")


def test_case1_30d_running_full_pass(flat_scenario: Scenario, tmp_path: Path) -> None:
    """(1) RUNNING + age 30d + metrics 30d + evidencia completa ⇒ PASS."""
    state_path = tmp_path / "certification-state.json"
    final = _progression(flat_scenario, state_path)
    assert certification_phase(final) == "RUNNING"
    assert final["operational"]["metrics_history_days"] == CERT_DAYS
    assert final["operational"]["accounting_residual"] == "0"
    assert final["operational"]["accounting_status"] == "PASS"
    assert final["operational"]["kill_switch_tested"] == "PASS"
    assert final["operational"]["daily_loss_tested"] == "PASS"
    assert final["operational"]["certification_reports_complete"] == "PASS"
    assert final["operational"]["market_evidence_complete"] == "PASS"
    assert final["operational"]["decision_context_coverage"] == 100.0

    report = _evaluate(final, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "PASS"
    assert report.certification_age_days >= 30.0
    assert report.failure_reasons == ()

    # Requisito 8 también cubre el estado del caso 1.
    _assert_strict_json(final)


def test_case2_age_29d_fails_calendar_days(flat_scenario: Scenario, tmp_path: Path) -> None:
    """(2) Evaluado en t0+29d ⇒ FAIL (calendar_days), aunque todo lo demás esté OK."""
    state_path = tmp_path / "certification-state.json"
    final = _progression(flat_scenario, state_path)
    report = _evaluate(final, at_ms=T0 + 29 * DAY_MS)
    assert report.overall_status == "FAIL"
    assert report.certification_age_days < 30.0
    assert _check(report, "calendar_days").status == "FAIL"
    assert any(reason.startswith("calendar_days") for reason in report.failure_reasons)
    _assert_strict_json(final)


def test_case3_30d_clock_29_heartbeats_fails_metrics(
    flat_scenario: Scenario, tmp_path: Path
) -> None:
    """(3) Reloj 30d pero solo 29 heartbeats ⇒ FAIL (metrics_history_days)."""
    state_path = tmp_path / "certification-state.json"
    final = _progression(flat_scenario, state_path, drop_heartbeat_day=15)
    assert certification_phase(final) == "RUNNING"
    assert final["operational"]["metrics_history_days"] == CERT_DAYS - 1
    report = _evaluate(final, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "FAIL"
    assert report.certification_age_days >= 30.0  # el reloj SÍ llegó a 30d
    assert _check(report, "metrics_history_days").status == "FAIL"
    assert any(reason.startswith("metrics_history_days") for reason in report.failure_reasons)
    _assert_strict_json(final)


def test_case4_accounting_corruption_fails_with_accounting_reason(
    open_scenario: Scenario, tmp_path: Path
) -> None:
    """(4) Corrupción compensada tras avanzar el libro ⇒ FAIL contable preservado.

    Se avanza el libro bueno 3 días (día 0 baseline, días 1-2 PASS con la posición
    abierta marcada a 110); el día 3 se alimentan eventos corruptos (fee↑ + price↓
    con equity final bit-igual) ⇒ reconciliation FAIL y el evaluador reporta la
    razón ``accounting_residual``.
    """
    state_path = tmp_path / "certification-state.json"
    good_events = [e for e in open_scenario.events if e.timestamp_ms <= T0 + 30 * DAY_MS]
    final = _progression(open_scenario, state_path, events=good_events)
    good_book = final["accounting_book"]
    assert final["operational"]["accounting_residual"] == "0"
    assert final["operational"]["accounting_status"] == "PASS"

    corrupt_events, _, _ = _open_position_events("e2e-open", corrupt=True)
    corrupt_events = [e for e in corrupt_events if e.timestamp_ms <= T0 + 30 * DAY_MS]
    now = T0 + 31 * DAY_MS  # escritura del día 30 con los eventos corruptos
    state = _build_state(
        final,
        open_scenario,
        now_ms=now,
        events=corrupt_events,
    )
    residual = state["operational"]["accounting_residual"]
    assert isinstance(residual, str)
    assert residual != "0"
    assert state["operational"]["accounting_status"] == "FAIL"
    assert state["operational"]["accounting_failure_reason"] == "accounting_mismatch"
    assert state["accounting_book"] == good_book  # el libro NO avanza con corrupción

    report = _evaluate(state, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "FAIL"
    assert any(reason.startswith("accounting_residual") for reason in report.failure_reasons)
    _assert_strict_json(state)


def test_case5_safeguard_artifact_mismatch_fails(flat_scenario: Scenario, tmp_path: Path) -> None:
    """(5) Safeguard evidence con risk_config_version distinta ⇒ FAIL safeguards.

    La evidencia de safeguards se relee en cada escritura periódica (fail-closed):
    un evidence file con ``risk_config_version`` distinta del frozen falla el
    matcher TODOS los días (el frozen ancla risk-v1).
    """
    state_path = tmp_path / "certification-state.json"
    mismatched = flat_scenario.safeguard(risk_config_version="risk-v2")
    # La evidencia con risk_config_version driftada es el archivo que relee el
    # runner en CADA escritura periódica ⇒ mismatch persistente día a día.
    evidence_by_day = {day: mismatched for day in range(CERT_DAYS)}
    final = _progression(flat_scenario, state_path, safeguards=evidence_by_day)

    assert final["operational"]["kill_switch_tested"] == "FAIL"
    assert final["operational"]["daily_loss_tested"] == "FAIL"
    report = _evaluate(final, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "FAIL"
    assert _check(report, "kill_switch_tested").status == "FAIL"
    assert _check(report, "daily_loss_tested").status == "FAIL"
    assert any(reason.startswith("kill_switch_tested") for reason in report.failure_reasons)
    assert any(reason.startswith("daily_loss_tested") for reason in report.failure_reasons)
    _assert_strict_json(final)


def test_case6_version_drift_fails_frozen_versions_no_reanchor(
    flat_scenario: Scenario, tmp_path: Path
) -> None:
    """(6) Drift de strategy_version (misma sesión) ⇒ frozen intacto, FAIL.

    El día 30 se alimenta un artefacto con ``strategy_version`` distinta. La
    identidad que preserva el ancla es el contexto de sesión (symbol/timeframe):
    el frozen previo (baseline-v1 anclado en t0) se conserva byte a byte, la fase
    sigue RUNNING y ``current`` refleja la versión driftada ⇒ el evaluador emite
    ``frozen_versions`` FAIL. El reloj NO se re-ancla.
    """
    state_path = tmp_path / "certification-state.json"
    final = _progression(flat_scenario, state_path)
    anchor = final["frozen"]["certification_started_at"]
    assert anchor is not None
    assert final["frozen"]["strategy_version"] == STRATEGY_VERSION

    now = T0 + CERT_DAYS * DAY_MS
    drifted = flat_scenario.artifact(now, strategy_version="baseline-v2")
    # Misma sesión (symbol/timeframe); safeguard ligado al frozen baseline-v1.
    state = _build_state(final, flat_scenario, now_ms=now, artifact=drifted)
    assert certification_phase(state) == "RUNNING"
    assert state["frozen"] == final["frozen"]  # byte a byte (anchor + versions)
    assert state["frozen"]["certification_started_at"] == anchor
    assert state["current"]["strategy_version"] == "baseline-v2"
    assert state["current"]["certification_started_at"] == anchor

    report = _evaluate(state, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "FAIL"
    assert _check(report, "frozen_versions").status == "FAIL"
    assert any(reason.startswith("frozen_versions") for reason in report.failure_reasons)
    _assert_strict_json(state)


def test_case7_not_started_never_passes(flat_scenario: Scenario, tmp_path: Path) -> None:
    """(7) Estado v2 sin START (ancla None) evaluado a 30d ⇒ FAIL, jamás PASS."""
    state_path = tmp_path / "certification-state.json"
    # Solo el día 0 sin start_certification ⇒ NOT_STARTED persistido.
    state = _build_state(
        {},
        flat_scenario,
        now_ms=T0 + DAY_MS,
    )
    assert certification_phase(state) == "NOT_STARTED"
    assert state["frozen"]["certification_started_at"] is None
    _write_state(state, state_path)

    report = _evaluate(state, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "FAIL"
    assert _check(report, "calendar_days").status == "FAIL"
    assert any(reason.startswith("calendar_days") for reason in report.failure_reasons)
    _assert_strict_json(state)


def test_case8_strict_json_no_nan_infinity(
    flat_scenario: Scenario, open_scenario: Scenario, tmp_path: Path
) -> None:
    """(8) JSON estricto (allow_nan=False) sobre estados PASS, FAIL y no auditables."""
    # Estado del caso 1 (PASS).
    state_path = tmp_path / "case1-state.json"
    final = _progression(flat_scenario, state_path)
    _assert_strict_json(final)

    # Estado con reconciliation_error="missing_persisted_mark" (posición abierta
    # sin velas): el productor emite residual None sin NaN.
    events = [e for e in open_scenario.events if e.timestamp_ms <= T0 + DAY_MS]
    no_candles_state = _build_state(
        {},
        open_scenario,
        now_ms=T0 + DAY_MS,
        events=events,
        candles=[],
        reconciliation_error="missing_persisted_mark",
    )
    assert no_candles_state["operational"]["accounting_residual"] is None
    assert no_candles_state["operational"]["accounting_failure_reason"] == "missing_persisted_mark"
    _assert_strict_json(no_candles_state)

    # Estado del caso 4 (corrupción contable compensada).
    good_events = [e for e in open_scenario.events if e.timestamp_ms <= T0 + 30 * DAY_MS]
    good_path = tmp_path / "case4-good.json"
    good_state = _progression(open_scenario, good_path, events=good_events)
    corrupt_events, _, _ = _open_position_events("e2e-open", corrupt=True)
    corrupt_events = [e for e in corrupt_events if e.timestamp_ms <= T0 + 30 * DAY_MS]
    corrupt_state = _build_state(
        good_state,
        open_scenario,
        now_ms=T0 + 31 * DAY_MS,
        events=corrupt_events,
    )
    assert corrupt_state["operational"]["accounting_status"] == "FAIL"
    _assert_strict_json(corrupt_state)


def test_case9_midrun_legit_fills_between_writes_pass(
    mid_run_scenario: Scenario, tmp_path: Path
) -> None:
    """(9, F2) Fills legítimos a mitad de corrida entre escrituras ⇒ PASS y libro avanza.

    El escenario mantiene una posición abierta a través de varias escrituras y
    ejecuta cierres legítimos los días 5 y 17: la reconciliación three-way
    (checkpoint con cursor) pasa en CADA escritura y el ``accounting_book`` avanza;
    el libro estático de Task 4b jamás podría reconciliar estos componentes que
    cambian legítimamente entre writes. Al final de 30 días la certificación PASS.
    """
    state_path = tmp_path / "certification-state.json"
    final = _progression(mid_run_scenario, state_path)
    assert certification_phase(final) == "RUNNING"
    assert final["operational"]["accounting_residual"] == "0"
    assert final["operational"]["accounting_status"] == "PASS"
    assert final["operational"]["accounting_failure_reason"] is None
    book = final["accounting_book"]
    assert isinstance(book, dict)
    assert book["last_event_ms"] is not None  # checkpoint con cursor actualizado

    report = _evaluate(final, at_ms=T0 + CERT_DAYS * DAY_MS)
    assert report.overall_status == "PASS"
    assert report.failure_reasons == ()
    _assert_strict_json(final)
