# Phase 04 — Real-Time Market Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development o superpowers:executing-plans. Steps usan checkbox (`- [ ]`).

**Goal:** Conectar a Bybit WebSocket producción (spot) para mantener un order book local sincronizado (snapshot+deltas con reconciliación de secuencia) y candles en vivo confirmadas al cierre, con reconexión automática, detección STALE y agregación de features de order book persistidas.

**Architecture:** Monolito hexagonal. `domain/market` (`OrderBook`, `MarketDataHealth`, eventos de stream puros), `application/ports` (`MarketDataStream`, repos de features), `application/services` (`MarketDataService` orquestación: order book + reconciliación + STALE + agregación), `infrastructure/bybit` (`BybitWebSocketClient` sobre `websockets`), `infrastructure/database` (tabla `orderbook_feature_windows`, migración 0003). El "Market Worker" (§63) se expone como subcomando CLI `market-worker`.

**Tech Stack:** `websockets` (async, ya presente transitiva vía `uvicorn[standard]`), Pydantic v2 (validación de mensajes WS), SQLAlchemy 2.x + Alembic, stdlib (`asyncio`, `decimal`/`float`).

## Global Constraints

- Sin instalación sin DP-005 APPROVED (PRD §11): `websockets` pasa de transitiva a runtime directa.
- Estructura hexagonal: `domain ← application ← interfaces`; `infrastructure` implementa puertos. Dominio puro (dataclasses, sin frameworks).
- Alembic para TODO cambio de esquema; migración con upgrade/downgrade + test roundtrip (PRD §56).
- Order book: nunca persistir cada delta bruto; persistir solo features agregadas (PRD §14).
- Pérdida de sincronización ⇒ `Market State = STALE` ⇒ no abrir posiciones (reconectar + resnapshot + reconciliar + verificar + marcar sano) (PRD §14).
- Solo vela confirmada dispara decisión (PRD §13.2): kline con `confirm:true`.
- BTCUSDT solo lectura (contexto); la decisión solo opera ETH (PRD §13).
- Reutilizar `market_candles` (Fase 03) para persistir candles confirmadas en vivo.
- Coverage `--cov=src --cov-branch --cov-fail-under=90`; mypy strict; ruff.
- Fixtures reales de WS grabados una vez y versionados para tests offline (bybit-integration).
- Grafo codebase-memory a la par (AGENTS.md §4.13): re-index tras commit.

---

### Task 1: DP-005 + USER GATE

**Files:** Create `docs/phases/04/DP-005-websockets-runtime.md`

**Produces:** decisión APPROVED que autoriza `uv add websockets` (runtime).

- [ ] **Step 1:** Escribir la proposal (runtime `websockets>=17`; ya presente transitiva por `uvicorn[standard]`; alternativa `aiohttp` descartada; rollback).
- [ ] **Step 2:** Presentar al usuario y esperar APPROVED.

---

### Task 2: Domain — OrderBook (TDD)

**Files:**
- Create: `src/domain/market/orderbook.py`
- Test: `tests/test_orderbook.py`

**Interfaces:**
- Produce `OrderBookLevel` (frozen dataclass: `price: float, size: float`).
- Produce `OrderBookDesync(Exception)`.
- Produce `MarketDataHealth(StrEnum)`: `HEALTHY = "healthy"`, `STALE = "stale"`.
- Produce `OrderBook` con: `apply_snapshot(bids, asks, update_id)`, `apply_delta(bids, asks, update_id)` (raise `OrderBookDesync` si `update_id > self.update_id + 1`; ignora `<=`), propiedades `best_bid`, `best_ask`, `mid`, `spread`, `spread_pct`, `depth(side, levels)`, `imbalance`, y `is_healthy`.

- [ ] **Step 1:** Test que falla

```python
import pytest

from domain.market.orderbook import OrderBook, OrderBookDesync

SNAP_BIDS = [(100.0, 1.0), (99.0, 2.0)]
SNAP_ASKS = [(101.0, 1.5), (102.0, 3.0)]


def test_snapshot_and_quotes() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    assert ob.best_bid == 100.0
    assert ob.best_ask == 101.0
    assert ob.mid == 100.5
    assert ob.spread == 1.0


def test_delta_updates_and_deletes() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    ob.apply_delta([(100.0, 0.0), (99.5, 2.5)], [(101.0, 0.0)], update_id=11)
    assert ob.best_bid == 99.5
    assert ob.best_ask == 102.0


def test_delta_gap_raises_desync() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    with pytest.raises(OrderBookDesync):
        ob.apply_delta([], [], update_id=13)


def test_delta_out_of_order_ignored() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot(SNAP_BIDS, SNAP_ASKS, update_id=10)
    ob.apply_delta([(99.5, 2.5)], [], update_id=11)
    ob.apply_delta([(99.4, 1.0)], [], update_id=10)  # <= last → ignorado
    assert ob.best_bid == 99.5


def test_depth_and_imbalance() -> None:
    ob = OrderBook("ETHUSDT")
    ob.apply_snapshot([(100.0, 1.0), (99.0, 2.0)], [(101.0, 1.5), (102.0, 3.0)], update_id=1)
    assert ob.depth("bids", 2) == 3.0
    assert ob.depth("asks", 2) == 4.5
    assert ob.imbalance == pytest.approx(3.0 / (3.0 + 4.5))
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implementar `src/domain/market/orderbook.py`

```python
"""Order book local y estado de salud del mercado (PRD §14). Sin frameworks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MarketDataHealth(StrEnum):
    HEALTHY = "healthy"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    size: float


class OrderBookDesync(Exception):
    """Se perdió la secuencia de deltas: el book puede estar corrupto."""


@dataclass
class OrderBook:
    symbol: str
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    update_id: int | None = None

    def apply_snapshot(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        update_id: int,
    ) -> None:
        self.bids = {p: s for p, s in bids if s > 0}
        self.asks = {p: s for p, s in asks if s > 0}
        self.update_id = update_id

    def apply_delta(
        self,
        bids: list[tuple[float, float]],
        asks: list[tuple[float, float]],
        update_id: int,
    ) -> None:
        if self.update_id is not None and update_id > self.update_id + 1:
            raise OrderBookDesync(
                f"gap en secuencia: esperado {self.update_id + 1}, recibido {update_id}"
            )
        if self.update_id is not None and update_id <= self.update_id:
            return
        self._apply_levels(self.bids, bids)
        self._apply_levels(self.asks, asks)
        self.update_id = update_id

    @staticmethod
    def _apply_levels(book: dict[float, float], levels: list[tuple[float, float]]) -> None:
        for price, size in levels:
            if size == 0:
                book.pop(price, None)
            else:
                book[price] = size

    @property
    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def spread_pct(self) -> float | None:
        if self.mid is None or self.spread is None or self.mid == 0:
            return None
        return self.spread / self.mid

    def depth(self, side: str, levels: int) -> float:
        book = self.bids if side == "bids" else self.asks
        prices = sorted(book, reverse=(side == "bids"))[:levels]
        return sum(book[p] for p in prices)

    @property
    def imbalance(self) -> float | None:
        bid_depth = self.depth("bids", 50)
        ask_depth = self.depth("asks", 50)
        total = bid_depth + ask_depth
        if total == 0:
            return None
        return bid_depth / total

    @property
    def is_healthy(self) -> bool:
        return self.best_bid is not None and self.best_ask is not None
```

- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit: `feat(phase-04): dominio OrderBook + MarketDataHealth`.

---

### Task 3: Domain — Eventos de stream (TDD)

**Files:**
- Create: `src/domain/market/stream.py`
- Test: `tests/test_stream_events.py`

**Interfaces:**
- Produce `OrderBookSnapshot(symbol, bids: tuple[OrderBookLevel, ...], asks: tuple[...], update_id: int, seq: int)`.
- Produce `OrderBookDelta(symbol, bids, asks, update_id, seq)`.
- Produce `KlineUpdate(symbol, interval: Timeframe, start_ms: int, open, high, low, close, volume, turnover: float, confirm: bool)` con `def to_candle() -> Candle | None` (None si no confirmada).

- [ ] **Step 1:** Test que falla

```python
from domain.market.candle import Candle, Timeframe
from domain.market.stream import KlineUpdate


def test_kline_confirmed_to_candle() -> None:
    k = KlineUpdate("ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=True)
    assert k.to_candle() == Candle(1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0)


def test_kline_unconfirmed_is_none() -> None:
    k = KlineUpdate("ETHUSDT", Timeframe.M15, 1000, 1.0, 2.0, 0.5, 1.5, 10.0, 20.0, confirm=False)
    assert k.to_candle() is None
```

- [ ] **Step 2:** Implementar `src/domain/market/stream.py` (dataclasses frozen; `KlineUpdate.to_candle()`).
- [ ] **Step 3:** Commit: `feat(phase-04): eventos de stream de market data`.

---

### Task 4: Application — Puertos (Protocols)

**Files:**
- Create: `src/application/ports/market_stream.py`
- Create: `src/application/ports/orderbook_features.py`

**Interfaces:**
- Produce `MarketDataStream` Protocol: `async connect()`, `async close()`, `async subscribe_orderbook(symbol, depth)`, `async subscribe_kline(symbol, interval)`, `async recv() -> StreamEvent` (unión de snapshot/delta/kline/desconexión).
- Produce `OrderBookFeatureRepository` Protocol: `async insert(symbol, feature) -> None`.

- [ ] **Step 1:** Escribir ambos Protocols (sin tests).

---

### Task 5: Infraestructura — BybitWebSocketClient (TDD con fixtures)

**Files:**
- Create: `src/infrastructure/bybit/ws.py`
- Create: `src/infrastructure/bybit/ws_schemas.py`
- Create: `tests/fixtures/bybit_ws_*.json` (grabados reales)
- Test: `tests/test_bybit_ws.py`

**Interfaces:**
- Produce `BybitWebSocketClient` con `__init__(url, connect_fn=...)` inyectable para tests, `connect/subscribe_*/recv/close`; parsea snapshot/delta/kline; responde `pong` a `ping`; expone reconexión vía excepción `WebSocketDisconnected`.

- [ ] **Step 1:** Grabar fixtures reales (snapshot, delta, kline, subscribe response, ping) con un script de captura.
- [ ] **Step 2:** Test con un `connect_fn` fake que devuelve un iterable de mensajes; verificar parseo de snapshot/delta/kline y respuesta a ping.
- [ ] **Step 3:** Implementar `ws.py` + `ws_schemas.py`.
- [ ] **Step 4:** Commit: `feat(phase-04): cliente WebSocket Bybit`.

---

### Task 6: Application — MarketDataService (TDD)

**Files:**
- Create: `src/application/services/market_data_service.py`
- Test: `tests/test_market_data_service.py`

**Interfaces:**
- Produce `MarketDataService(stream, candle_repo, feature_repo, config)`: mantiene `OrderBook` por símbolo, reconcilia secuencia, marca STALE ante gap o timeout, emite candles confirmadas (upsert a `market_candles`), y agrega features de order book a `orderbook_feature_windows` en un intervalo. Propiedad `health -> MarketDataHealth`.

- [ ] **Step 1:** Test con stream fake: snapshot+deltas→book sano; gap→STALE+resubscribe; kline confirm→upsert; kline unconfirmed→ignorado.
- [ ] **Step 2:** Implementar.
- [ ] **Step 3:** Commit: `feat(phase-04): MarketDataService (reconciliación + STALE + agregación)`.

---

### Task 7: Infraestructura — Migración 0003 + repositorio (integración, TDD)

**Files:**
- Create: `migrations/versions/0003_orderbook_features.py`
- Modify: `src/infrastructure/database/models.py`, `src/infrastructure/database/repositories.py`
- Test: `tests/integration/test_orderbook_features.py`

**Interfaces:**
- Produce ORM `OrderBookFeatureWindow` (tabla `orderbook_feature_windows`: symbol, window_start_ms, window_end_ms, best_bid, best_ask, spread, spread_pct, bid_depth, ask_depth, imbalance, created_at).
- Produce `SqlAlchemyOrderBookFeatureRepository`.

- [ ] **Step 1–4:** Modelo + migración + repo + test roundtrip (up→down→up) + insert/query.
- [ ] **Step 5:** Commit: `feat(phase-04): orderbook_feature_windows (migración 0003)`.

---

### Task 8: Interfaces — CLI `market-worker` + config (TDD)

**Files:**
- Modify: `src/interfaces/cli/market_worker.py` (nuevo), `src/main.py`, `src/settings.py`, `config/base.yaml`
- Test: `tests/test_cli_market_worker.py`

**Interfaces:**
- Produce subcomando `market-worker` que compone `BybitWebSocketClient` + `MarketDataService` y corre hasta Ctrl+C (o `--seconds N` para smoke tests).
- Settings: `bybit_ws_url`, `bybit_orderbook_depth`, `stale_timeout_seconds`, `feature_window_seconds`.

- [ ] **Step 1–4:** Config + CLI + tests de parsing (help, args).
- [ ] **Step 5:** Commit: `feat(phase-04): CLI market-worker`.

---

### Task 9: E2E real + evidencias + gate

- [ ] **Step 1:** Smoke test real: `market-worker --seconds 20` capturando snapshot+deltas+kline y persistiendo features; evidencia `ws-smoke.log`.
- [ ] **Step 2:** `pytest --cov --cov-fail-under=90` → coverage.json; ruff/format/mypy → logs.
- [ ] **Step 3:** `gate_check.py --phase 04` (0 FAIL); `progress.py mark-done` por entregable.
- [ ] **Step 4:** Reporte 30 secciones + UAT + gate-request.

---

## Self-Review

- **Spec coverage:** PRD §13.2 (candles confirmadas) → Task 3,6; §14 (order book local, snapshot/delta, STALE, reconexión, features agregadas) → Tasks 2,5,6,7; Fase 04 entregables (WS producción, candles, order book, snapshots/deltas, reconnect, stale, BTC contexto, agregación) → Tasks 5,6,7,8; §63 (Market Worker) → Task 8; §62 (métricas técnicas) → observabilidad diferida a Fase 13.
- **Type consistency:** `OrderBook` (bids/asks dict, update_id), eventos `OrderBookSnapshot/Delta/KlineUpdate`, `MarketDataHealth` (HEALTHY/STALE) usados consistentemente en service y client.
- **Placeholder scan:** sin TBD/TODO.

## Execution Handoff

Plan guardado en `docs/superpowers/plans/2026-08-23-phase-04-real-time-market-data.md`.
