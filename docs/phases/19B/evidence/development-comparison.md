# Phase 19B — DEVELOPMENT Economic Evaluation (baseline vs Donchian)

- A baseline-v1: `8979ff8479d9e17ccc17da52f81f1fe25d7c83b5a69419257f307a151929da67`
- B EthDonchianBreakout-v1: `9fa8f8e4a67da2e742e89c8bac74145e5bac02937f7e5b94b5363ee382216e45`
- Slice: DEVELOPMENT `[0, 62208)`
- SpecIds differ: `True`
- Reproducibility: `PASS`
- Development result: `IMPROVED`
- Walk-forward candidate: `YES`
- Edge present: `NOT_EVALUATED_OUT_OF_SAMPLE`
- Strategy promotable: `NOT_EVALUATED`

| Metric | baseline-v1 | EthDonchianBreakout-v1 | Delta |
|---|---|---|---|
| signals_buy | 634 | 2035 | 1401.000000 |
| signals_sell | 1021 | 4005 | 2984.000000 |
| signals_hold | 60553 | 56168 | -4385.000000 |
| fills | 812 | 812 | 0.000000 |
| closed_trades | 406 | 406 | 0.000000 |
| net_pnl | -20.023554 | -20.008372 | 0.015181 |
| return_pct | -0.020024 | -0.020008 | 0.000015 |
| fees | 16.242716 | 16.242731 | 0.000015 |
| slippage | 3.248543 | 3.248546 | 0.000003 |
| max_drawdown | 0.016775 | 0.017006 | 0.000231 |
| profit_factor | 0.390291 | 0.422239 | 0.031948 |
| expectancy | -0.049319 | -0.049282 | 0.000037 |
| win_rate | 0.083744 | 0.105911 | 0.022167 |
| average_win | 0.376988 | 0.340058 | -0.036930 |
| average_loss | -0.088283 | -0.095402 | -0.007119 |

## Primary deltas (Donchian vs Baseline)

- DELTA_NET_PNL: `0.015181`
- DELTA_RETURN_PCT: `0.000015`
- DELTA_MAX_DRAWDOWN: `0.000231`
- DELTA_PROFIT_FACTOR: `0.031948`
- DELTA_EXPECTANCY: `0.000037`
- DELTA_WIN_RATE: `0.022167`
- DELTA_TRADES: `0`
- DELTA_FEES: `0.000015`
- DELTA_SLIPPAGE: `0.000003`

## Signal / execution attribution (EthDonchianBreakout-v1)

- DONCHIAN_BUY_SIGNALS: `2035`
- DONCHIAN_SELL_SIGNALS: `4005`
- EXECUTED_BUYS: `406`
- EXECUTED_SELLS: `406`
- REJECTED_BUYS: `1629`
- SELL_SIGNALS_WITHOUT_POSITION: `1237`
- SUPERSEDED_BUYS (signal overridden by an exit on the same candle): `0`

## ADX / breakout diagnostics (descriptive)

- RAW_BREAKOUT_EVENTS: `2970`
- BREAKOUTS_CONFIRMED_BY_ADX: `2035`
- BREAKOUTS_BLOCKED_BY_ADX: `935`

Diagnostic only; ADX_MIN is not tuned from these results.

## Trade structure

| Metric | baseline-v1 | EthDonchianBreakout-v1 |
|---|---|---|
| average_holding_duration_ms | 8264039.408867 | 7040394.088670 |
| median_holding_duration_ms | 900000.000000 | 900000.000000 |
| average_trade_pnl | -0.049319 | -0.049282 |
| largest_win | 2.403399 | 1.257031 |
| largest_loss | -0.419478 | -0.494060 |

## Predeclared interpretation

IMPROVED iff expectancy, profit factor and net PnL improve while max drawdown does not worsen by more than `0.010000` absolute; NOT_IMPROVED when no metric improves or at least two of the three economic metrics deteriorate; otherwise MIXED. No composite score.

## Safety

- WALK_FORWARD_READS: `0`
- FINAL_HOLDOUT_READS: `0`
- FINAL_HOLDOUT_EXECUTIONS: `0`
- HOLDOUT_STATE: `PRISTINE`

Development may orient which candidate deserves to advance, but it does not demonstrate out-of-sample edge. EDGE_PRESENT and STRATEGY_PROMOTABLE remain NOT_EVALUATED.
