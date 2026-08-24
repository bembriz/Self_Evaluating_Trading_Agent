from domain.market.candle import Candle
from domain.market.indicators import ema, rsi
from domain.trading.signal import Action
from domain.trading.strategy import EmaRsiBaseline, EmaRsiConfig


def _c(ts: int, close: float) -> Candle:
    return Candle(ts, close, close, close, close, 1.0, close)


def _series(closes: list[float]) -> list[Candle]:
    return [_c(i * 3600_000, c) for i, c in enumerate(closes)]


def _reference_signals(closes: list[float], cfg: EmaRsiConfig) -> list[Action]:
    ema_f = ema(closes, cfg.ema_fast)
    ema_s = ema(closes, cfg.ema_slow)
    rsi_s = rsi(closes, cfg.rsi_period)
    out: list[Action] = []
    for i in range(len(closes)):
        if i == 0:
            out.append(Action.HOLD)
            continue
        f_prev = ema_f[i - 1]
        f_cur = ema_f[i]
        s_prev = ema_s[i - 1]
        s_cur = ema_s[i]
        r = rsi_s[i]
        if f_prev is None or f_cur is None or s_prev is None or s_cur is None or r is None:
            out.append(Action.HOLD)
            continue
        crossed_up = f_prev <= s_prev and f_cur > s_cur
        crossed_down = f_prev >= s_prev and f_cur < s_cur
        if crossed_up:
            out.append(Action.BUY)
        elif crossed_down or r > cfg.rsi_exit:
            out.append(Action.SELL)
        else:
            out.append(Action.HOLD)
    return out


def test_version() -> None:
    assert EmaRsiBaseline().version == "baseline-v1"


def test_incremental_matches_batch_indicators() -> None:
    closes = [100.0 + i * 0.3 + (0.5 if i % 2 else -0.5) for i in range(300)]
    strat = EmaRsiBaseline()
    got = [strat.on_candle(c).action for c in _series(closes)]
    expected = _reference_signals(closes, EmaRsiConfig())
    assert got == expected


def test_hold_during_warmup() -> None:
    strat = EmaRsiBaseline()
    actions = [strat.on_candle(c).action for c in _series([100.0] * 51)]
    assert all(a is Action.HOLD for a in actions)


def test_buy_on_uptrend_cross() -> None:
    closes = [100.0] * 80 + [100.0 + i * 0.1 for i in range(120)]
    strat = EmaRsiBaseline()
    actions = [strat.on_candle(c).action for c in _series(closes)]
    assert Action.BUY in actions


def test_sell_on_downtrend_cross() -> None:
    closes = [100.0] * 80 + [100.0 - i * 0.2 for i in range(120)]
    strat = EmaRsiBaseline()
    actions = [strat.on_candle(c).action for c in _series(closes)]
    assert Action.SELL in actions


def test_sell_on_rsi_overbought() -> None:
    closes = [100.0 * (1.02**i) for i in range(120)]
    strat = EmaRsiBaseline()
    actions = [strat.on_candle(c).action for c in _series(closes)]
    assert Action.SELL in actions
