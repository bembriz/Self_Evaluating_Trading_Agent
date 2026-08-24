# Phase 05 — Feature Engine & Market State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el Feature Engine puro (dominio) que transforma candles multi-timeframe + order book + contexto BTC en un `MarketState` versionado con régimen determinista, sin información futura.

**Architecture:** Código 100% puro en `src/domain/market/` (cero I/O, cero frameworks). Indicadores implementados internamente en Python stdlib (PRD §15: no TA-Lib/numpy sin justificar → ADR-0002). El `FeatureEngine` ensambla un `MarketState` inmutable (dataclass frozen) a partir de candles por timeframe, snapshot de features de order book y candles BTC de solo lectura.

**Tech Stack:** Python 3.12 stdlib (`math`, `statistics`), dataclasses, `StrEnum`. Sin dependencias nuevas.

## Global Constraints

- Sin dependencias nuevas (no numpy/pandas/TA-Lib) — indicadores en stdlib puro (PRD §15).
- Regla hexagonal dura: `domain/` no importa `infrastructure/`; todo en `domain/market/` es puro.
- Causalidad estricta (PRD §34): una feature en `t` usa solo candles cerradas `<= t`. La vela actual solo entra si está confirmada (las `Candle` ya lo están por construcción; `KlineUpdate.to_candle()` devuelve `None` si no confirma).
- Estilo: `from __future__ import annotations`, `dataclass(frozen=True, slots=True)`, `StrEnum`, `list[float | None]` para warmup.
- Lint/typing: `ruff check .`, `ruff format --check .`, `mypy src tests` (strict).
- Cobertura: `uv run pytest --cov=src --cov-branch --cov-fail-under=90`.

---

### Task 1: Indicadores técnicos puros

**Files:**
- Create: `src/domain/market/indicators.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Consumes: `domain.market.candle.Candle` (solo lectura).
- Produces (importados por Tasks 2–3):
  - `sma(values: Sequence[float], period: int) -> list[float | None]`
  - `ema(values: Sequence[float], period: int) -> list[float | None]`
  - `rsi(values: Sequence[float], period: int = 14) -> list[float | None]`
  - `macd(values: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MACDResult`
  - `MACDResult(macd: list[float | None], signal: list[float | None], histogram: list[float | None])`
  - `atr(candles: Sequence[Candle], period: int = 14) -> list[float | None]`
  - `vwap(candles: Sequence[Candle]) -> list[float | None]`
  - `returns(values: Sequence[float]) -> list[float | None]`
  - `realized_volatility(values: Sequence[float], window: int) -> list[float | None]`
  - `momentum(values: Sequence[float], window: int) -> list[float | None]`
  - `relative_volume(candles: Sequence[Candle], window: int) -> list[float | None]`

**Convenciones de implementación (causal, documentadas):**
- `ema` se siembra con SMA de los primeros `period` valores en el índice `period-1`; luego `alpha=2/(period+1)`.
- `rsi` (Wilder): necesita `period+1` precios; primer valor en índice `period`; `avg_loss==0` ⇒ `100.0` si `avg_gain>0` else `50.0`.
- `atr` (Wilder): TR estándar; primer valor en índice `period`.
- `vwap`: acumulado de sesión sobre la serie recibida (`typical=(h+l+c)/3`); `None` si volumen acumulado 0.
- `returns[i]=(v[i]-v[i-1])/v[i-1]`; `None` si divisor 0.
- `realized_volatility`: desviación estándar muestral (ddof=1) de `returns` en ventana; requiere ≥2 retornos.
- `momentum[i]=(v[i]-v[i-window])/v[i-window]`.
- `relative_volume[i]=volume[i]/mean(volume[i-window+1..i])`.
- `period<=0` ⇒ `ValueError`. Secuencia vacía ⇒ lista vacía.

- [ ] **Step 1: Escribir tests que fallan** — `tests/test_indicators.py`

```python
import pytest

from domain.market.candle import Candle
from domain.market.indicators import (
    atr, ema, macd, momentum, realized_volatility, relative_volume,
    returns, rsi, sma, vwap,
)


def _c(o, h, l, c, v=1.0) -> Candle:
    return Candle(timestamp_ms=0, open=o, high=h, low=l, close=c, volume=v, turnover=v * c)


def test_sma_warmup_and_values() -> None:
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = sma(vals, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[4] == pytest.approx(4.0)


def test_ema_seeded_with_sma() -> None:
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = ema(vals, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    # alpha = 2/4 = 0.5 ; ema[3] = 0.5*4 + 0.5*2 = 3
    assert out[3] == pytest.approx(3.0)


def test_rsi_flat_is_50_uptrend_is_100() -> None:
    flat = [10.0] * 20
    out_flat = rsi(flat, 14)
    assert out_flat[14] == pytest.approx(50.0)
    up = [float(i) for i in range(30)]
    out_up = rsi(up, 14)
    assert out_up[14] == pytest.approx(100.0)


def test_rsi_downtrend_is_0() -> None:
    down = [float(30 - i) for i in range(30)]
    out = rsi(down, 14)
    assert out[14] == pytest.approx(0.0)


def test_macd_histogram_equals_macd_minus_signal() -> None:
    vals = [float(i) for i in range(1, 100)]
    m = macd(vals, 12, 26, 9)
    assert len(m.macd) == len(vals)
    for i in range(len(vals)):
        if m.macd[i] is not None and m.signal[i] is not None:
            assert m.histogram[i] == pytest.approx(m.macd[i] - m.signal[i])


def test_atr_constant_range() -> None:
    candles = [_c(100, 110, 90, 100) for _ in range(30)]
    out = atr(candles, 14)
    assert out[14] == pytest.approx(20.0)
    assert out[29] == pytest.approx(20.0)


def test_vwap_cumulative() -> None:
    candles = [
        _c(100, 100, 100, 100, v=2.0),
        _c(100, 110, 100, 110, v=2.0),
    ]
    out = vwap(candles)
    # typical: 100 y (110+100+110)/3=106.667; pv: 200 + 213.333=413.333; vol 4
    assert out[1] == pytest.approx(413.3333 / 4.0)


def test_returns_and_momentum() -> None:
    vals = [10.0, 11.0, 12.1]
    assert returns(vals)[0] is None
    assert returns(vals)[1] == pytest.approx(0.1)
    assert momentum(vals, 2)[2] == pytest.approx(0.21)


def test_realized_volatility_requires_two_returns() -> None:
    out = realized_volatility([10.0, 11.0, 12.0], 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] is not None


def test_relative_volume() -> None:
    candles = [_c(100, 100, 100, 100, v=v) for v in (10.0, 10.0, 20.0)]
    out = relative_volume(candles, 3)
    assert out[2] == pytest.approx(20.0 / (40.0 / 3.0))


def test_invalid_period_raises() -> None:
    with pytest.raises(ValueError):
        sma([1.0, 2.0], 0)
```

- [ ] **Step 2: Verificar fallo** — `uv run pytest tests/test_indicators.py -v` ⇒ FAIL (módulo inexistente).
- [ ] **Step 3: Implementar** — `src/domain/market/indicators.py` (ver fórmulas arriba).
- [ ] **Step 4: Verificar verde** — `uv run pytest tests/test_indicators.py -v` ⇒ PASS.
- [ ] **Step 5: Commit** (al final de la fase; ver flujo-commits).

---

### Task 2: Clasificación determinista de régimen

**Files:**
- Create: `src/domain/market/regime.py`
- Test: `tests/test_regime.py`

**Interfaces:**
- Consumes: `domain.market.indicators.ema`, `realized_volatility`; `domain.market.candle.Candle`.
- Produces:
  - `MarketRegime(StrEnum)`: `TREND_UP`, `TREND_DOWN`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `BREAKOUT`.
  - `RegimeConfig(frozen)`: `ema_fast=20, ema_slow=50, vol_window=20, vol_baseline=100, breakout_lookback=20, high_vol_threshold=1.5, low_vol_threshold=0.5, trend_threshold=0.005`.
  - `RegimeClassifier(version="regime-v1")` con `classify(candles: Sequence[Candle]) -> MarketRegime | None`.

**Algoritmo (prioridad, causal, sobre la última vela):**
1. `< 2` velas ⇒ `None`.
2. `BREAKOUT` si `close > max(high[-lookback-1:-1])` o `close < min(low[-lookback-1:-1])` (excluye la vela actual).
3. Ratio de volatilidad = `vol_now` (`vol_window`) / baseline (media de `vol_window` sobre `vol_baseline` velas; si insuficiente, baseline=vol_now ⇒ ratio 1.0). `>=high_vol_threshold` ⇒ `HIGH_VOLATILITY`; `<=low_vol_threshold` ⇒ `LOW_VOLATILITY`.
4. `diff=(ema_fast-ema_slow)/ema_slow`; `>trend_threshold` ⇒ `TREND_UP`; `< -trend_threshold` ⇒ `TREND_DOWN`.
5. `SIDEWAYS`.

- [ ] **Step 1: Escribir tests** — `tests/test_regime.py`

```python
from domain.market.candle import Candle
from domain.market.regime import MarketRegime, RegimeClassifier, RegimeConfig


def _c(ts, o, h, l, c, v=1.0) -> Candle:
    return Candle(timestamp_ms=ts, open=o, high=h, low=l, close=c, volume=v, turnover=v * c)


def _uptrend(n=120, start=100.0) -> list[Candle]:
    return [_c(i, start + i, start + i + 2, start + i - 1, start + i + 1) for i in range(n)]


def _downtrend(n=120, start=200.0) -> list[Candle]:
    return [_c(i, start - i, start - i + 1, start - i - 2, start - i - 1) for i in range(n)]


def test_classifier_versioned() -> None:
    assert RegimeClassifier().version == "regime-v1"


def test_not_enough_data_returns_none() -> None:
    assert RegimeClassifier().classify([_c(0, 100, 100, 100, 100)]) is None


def test_uptrend() -> None:
    assert RegimeClassifier().classify(_uptrend()) is MarketRegime.TREND_UP


def test_downtrend() -> None:
    assert RegimeClassifier().classify(_downtrend()) is MarketRegime.TREND_DOWN


def test_breakout_priority() -> None:
    flat = [_c(i, 100, 101, 99, 100) for i in range(60)]
    flat.append(_c(60, 100, 130, 100, 130))  # cierra muy por encima del rango previo
    assert RegimeClassifier().classify(flat) is MarketRegime.BREAKOUT


def test_high_volatility() -> None:
    candles = []
    for i in range(140):
        candles.append(_c(i, 100, 100 + (i % 2) * 30, 100 - (i % 2) * 30, 100))
    cfg = RegimeConfig(vol_baseline=40)
    assert RegimeClassifier(cfg).classify(candles) is MarketRegime.HIGH_VOLATILITY
```

- [ ] **Step 2: Verificar fallo.**
- [ ] **Step 3: Implementar** `src/domain/market/regime.py`.
- [ ] **Step 4: Verificar verde.**
- [ ] **Step 5: Commit** (fase).

---

### Task 3: MarketState y FeatureEngine

**Files:**
- Create: `src/domain/market/state.py`
- Create: `src/domain/market/feature_engine.py`
- Test: `tests/test_feature_engine.py`

**Interfaces:**
- Consumes: `domain.market.candle.{Candle, Timeframe}`, `domain.market.orderbook.MarketDataHealth`, `domain.market.features.OrderBookFeatureSnapshot`, `domain.market.indicators.*`, `domain.market.regime.{MarketRegime, RegimeClassifier}`.
- Produces:
  - `TimeframeFeatures` (frozen): `timeframe: Timeframe`, `close: float | None`, `ema_fast`, `ema_slow`, `rsi`, `atr`, `vwap`, `macd`, `macd_signal`, `macd_histogram`, `momentum`, `realized_volatility`, `relative_volume` (todo `float | None`).
  - `BtcContext` (frozen): `symbol: str`, `close: float | None`, `momentum: float | None`, `rsi: float | None`.
  - `MarketState` (frozen): `symbol: str`, `timestamp_ms: int`, `health: MarketDataHealth`, `regime: MarketRegime | None`, `timeframes: dict[Timeframe, TimeframeFeatures]`, `orderbook: OrderBookFeatureSnapshot | None`, `btc: BtcContext | None`.
  - `FeatureEngineConfig` (frozen): `rsi_period=14, ema_fast=20, ema_slow=50, macd_fast=12, macd_slow=26, macd_signal=9, atr_period=14, momentum_period=20, realized_vol_window=20, relative_volume_window=20, regime_timeframe=Timeframe.H1`.
  - `FeatureEngine.compute_state(symbol, health, candles_by_timeframe, orderbook=None, btc_candles=None) -> MarketState`.

**Reglas de `compute_state`:**
- `timestamp_ms` = max del último `timestamp_ms` por timeframe (0 si sin candles).
- Por timeframe: `TimeframeFeatures` con el último valor de cada indicador.
- `regime`: clasifica sobre las candles de `regime_timeframe` (default H1); si faltan, sobre el timeframe con más candles; si ninguno ⇒ `None`.
- `btc`: desde `btc_candles` (`close`, `momentum`, `rsi`); `symbol="BTCUSDT"`.
- Los indicadores usan series de `close` (y OHLCV para ATR/VWAP/rel_vol).

- [ ] **Step 1: Escribir tests** — `tests/test_feature_engine.py`

```python
from domain.market.candle import Candle, Timeframe
from domain.market.feature_engine import FeatureEngine, FeatureEngineConfig
from domain.market.orderbook import MarketDataHealth
from domain.market.regime import MarketRegime


def _c(ts, o, h, l, c, v=1.0) -> Candle:
    return Candle(timestamp_ms=ts, open=o, high=h, low=l, close=c, volume=v, turnover=v * c)


def _series(n, start=100.0) -> list[Candle]:
    return [_c(i * 3600_000, start + i, start + i + 2, start + i - 1, start + i + 1) for i in range(n)]


def test_computes_timeframe_features() -> None:
    candles = _series(200)
    engine = FeatureEngine()
    state = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY,
        {Timeframe.H1: candles},
    )
    assert state.symbol == "ETHUSDT"
    assert state.health is MarketDataHealth.HEALTHY
    tf = state.timeframes[Timeframe.H1]
    assert tf.close == pytest.approx(299.0)
    assert tf.rsi is not None
    assert tf.atr is not None
    assert tf.macd is not None


def test_timestamp_is_max_across_timeframes() -> None:
    engine = FeatureEngine()
    state = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY,
        {Timeframe.M15: _series(50), Timeframe.H1: _series(10)},
    )
    assert state.timestamp_ms == 9 * 3600_000


def test_regime_from_default_timeframe() -> None:
    engine = FeatureEngine()
    state = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY,
        {Timeframe.M15: _series(200), Timeframe.H1: _series(120)},
    )
    assert state.regime is MarketRegime.TREND_UP


def test_btc_context_read_only() -> None:
    engine = FeatureEngine()
    state = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY,
        {Timeframe.H1: _series(120)},
        btc_candles=_series(120, start=30000.0),
    )
    assert state.btc is not None
    assert state.btc.symbol == "BTCUSDT"
    assert state.btc.close is not None
    assert state.btc.rsi is not None


def test_empty_input() -> None:
    state = FeatureEngine().compute_state("ETHUSDT", MarketDataHealth.STALE, {})
    assert state.timestamp_ms == 0
    assert state.regime is None
    assert state.timeframes == {}
    assert state.btc is None
```

- [ ] **Step 2: Verificar fallo.**
- [ ] **Step 3: Implementar** `src/domain/market/state.py` y `src/domain/market/feature_engine.py`.
- [ ] **Step 4: Verificar verde.**
- [ ] **Step 5: Commit** (fase).

---

### Task 4: Tests anti-lookahead

**Files:**
- Create: `tests/test_no_lookahead.py`

**Interfaces:**
- Consumes: `domain.market.indicators.*`, `domain.market.regime.RegimeClassifier`, `domain.market.feature_engine.FeatureEngine`.

- [ ] **Step 1: Escribir tests** — patrón de la skill `data-leakage` (corruptor temporal + replay truncado):

```python
import pytest

from domain.market.candle import Candle, Timeframe
from domain.market.feature_engine import FeatureEngine
from domain.market.indicators import ema, macd, rsi
from domain.market.orderbook import MarketDataHealth
from domain.market.regime import RegimeClassifier


def _series(n, start=100.0, step=0.5) -> list[Candle]:
    out = []
    for i in range(n):
        o = start + i * step
        out.append(Candle(i * 3600_000, o, o + 2, o - 1, o + 1, 1.0, 1.0 * (o + 1)))
    return out


def test_ema_no_lookahead() -> None:
    candles = _series(150)
    closes = [c.close for c in candles]
    base = ema(closes, 20)
    # envenenar el futuro: cambiar closes desde el índice 100 en adelante
    poisoned = closes[:100] + [10**9] * (len(closes) - 100)
    poisoned_out = ema(poisoned, 20)
    assert poisoned_out[:100] == base[:100]


def test_rsi_no_lookahead() -> None:
    candles = _series(150)
    closes = [c.close for c in candles]
    base = rsi(closes, 14)
    poisoned = closes[:100] + [1e-9] * (len(closes) - 100)
    assert rsi(poisoned, 14)[:100] == base[:100]


def test_macd_no_lookahead() -> None:
    candles = _series(150)
    closes = [c.close for c in candles]
    base = macd(closes).macd
    poisoned = closes[:100] + [10**9] * (len(closes) - 100)
    assert macd(poisoned).macd[:100] == base[:100]


def test_regime_no_lookahead() -> None:
    candles = _series(150)
    base = RegimeClassifier().classify(candles[:100])
    poisoned = candles[:100] + [_poisoned_candle(i) for i in range(100, 150)]
    assert RegimeClassifier().classify(poisoned[:100]) == base


def _poisoned_candle(i: int) -> Candle:
    return Candle(i * 3600_000, 10**9, 10**9, 10**9, 10**9, 0.0, 0.0)


def test_market_state_no_lookahead() -> None:
    candles = _series(150)
    engine = FeatureEngine()
    base = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles[:100]}
    )
    poisoned = candles[:100] + [_poisoned_candle(i) for i in range(100, 150)]
    replay = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: poisoned[:100]}
    )
    assert replay == base


def test_replay_truncated_identical() -> None:
    candles = _series(150)
    engine = FeatureEngine()
    full = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles}
    )
    truncated = engine.compute_state(
        "ETHUSDT", MarketDataHealth.HEALTHY, {Timeframe.H1: candles[:120]}
    )
    assert truncated.timestamp_ms < full.timestamp_ms
```

- [ ] **Step 2: Verificar fallo.**
- [ ] **Step 3: Ajustar implementación si algún test falla (no debería: todo es causal).**
- [ ] **Step 4: Verificar verde.**
- [ ] **Step 5: Commit** (fase).

---

### Task 5: ADR, evidencia, gate y reporte

**Files:**
- Create: `docs/adr/ADR-0002-feature-engine-pure-python.md`
- Modify: `harness/state/progress.yaml` (vía scripts)

- [ ] **Step 1:** ADR-0002 (decisión indicadores stdlib puro + régimen versionado `regime-v1`).
- [ ] **Step 2:** Suite completa y cobertura:

```bash
uv run pytest --cov=src --cov-branch --cov-fail-under=90
```

- [ ] **Step 3:** Lint/typing/format:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
```

- [ ] **Step 4:** Registrar evidencia con `harness/scripts/evidence.sh` (unit-tests, coverage, lint, format, typing).
- [ ] **Step 5:** Marcar los 6 entregables `done` vía `progress.py mark-done` (evidencia por entregable).
- [ ] **Step 6:** `gate_check.py --phase 05` ⇒ 0 FAIL.
- [ ] **Step 7:** Completar reporte (30 secciones) y UAT; `gate-request`; esperar USER APPROVAL.

---

## Self-Review

- **Spec coverage:** Fase 05 PRD §15 (features: RSI/MACD/EMA/ATR/VWAP + returns/vol/momentum/rel-vol) → Task 1; §16 (regime determinista versionado) → Task 2; §14 features order book (spread/imbalance/depth) ya en `OrderBook`/`OrderBookFeatureSnapshot` → consumidas en Task 3; BTC contexto → Task 3; multi-timeframe state → Task 3; no-lookahead (§34) → Task 4. Entrega "no-lookahead-tests" cubierta. ✓
- **Placeholders:** ninguna fórmula ni test TBD. ✓
- **Type consistency:** firmas de `ema/atr/…`, `MACDResult`, `RegimeClassifier`, `FeatureEngine.compute_state` coinciden entre Tasks. ✓
