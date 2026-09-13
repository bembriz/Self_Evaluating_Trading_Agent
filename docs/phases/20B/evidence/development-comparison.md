# Phase 20B — DEVELOPMENT Economic Evaluation (baseline vs Bollinger)

- A baseline-v1: `281d065eb613c5e05869efc6b7a4d680ddc0c87b721502325224ea80d39a5dde`
- B EthBollingerMeanReversion-v1: `548b99560d9487e2b7cc745a6f411bcc60ac919fcaf5bfdc619c9ee46af14c04`
- Slice: DEVELOPMENT `[0, 62208)`
- SpecIds differ: `True`
- Baseline identity changed: `True`
- Baseline behavior changed: `False`
- Reproducibility: `PASS`
- Development result: `NOT_IMPROVED`
- Absolute viability gate: `FAIL`
- Walk-forward eligible: `NO` (authorized: `NO`)
- Edge present: `NOT_EVALUATED_OUT_OF_SAMPLE`
- Strategy promotable: `NOT_EVALUATED`

| Metric | baseline-v1 | EthBollingerMeanReversion-v1 | Delta |
|---|---|---|---|
| signals_buy | 634 | 460 | -174.000000 |
| signals_sell | 1021 | 32150 | 31129.000000 |
| signals_hold | 60553 | 29598 | -30955.000000 |
| fills | 812 | 806 | -6.000000 |
| closed_trades | 406 | 403 | -3.000000 |
| net_pnl | -20.023554 | -20.131280 | -0.107727 |
| return_pct | -0.020024 | -0.020131 | -0.000108 |
| fees | 16.242716 | 16.122440 | -0.120276 |
| slippage | 3.248543 | 3.224488 | -0.024055 |
| max_drawdown | 0.016775 | 0.016907 | 0.000132 |
| profit_factor | 0.390291 | 0.285582 | -0.104709 |
| expectancy | -0.049319 | -0.049954 | -0.000634 |
| win_rate | 0.083744 | 0.218362 | 0.134618 |
| average_win | 0.376988 | 0.091446 | -0.285542 |
| average_loss | -0.088283 | -0.089456 | -0.001173 |

## Primary deltas (Bollinger vs Baseline)

- DELTA_NET_PNL: `-0.107727`
- DELTA_RETURN_PCT: `-0.000108`
- DELTA_MAX_DRAWDOWN: `0.000132`
- DELTA_PROFIT_FACTOR: `-0.104709`
- DELTA_EXPECTANCY: `-0.000634`
- DELTA_WIN_RATE: `0.134618`
- DELTA_TRADES: `-3`
- DELTA_FEES: `-0.120276`
- DELTA_SLIPPAGE: `-0.024055`

## Absolute viability (Phase 19C)

- NET_PNL_GT_0: `False`
- EXPECTANCY_GT_0: `False`
- PROFIT_FACTOR_GT_1: `False`
- ABSOLUTE_VIABILITY_GATE: `FAIL`

## Mean-reversion diagnostics (descriptive)

- RAW_LOWER_BAND_EXCURSIONS: `3955`
- REENTRY_EVENTS: `1996`
- REENTRIES_CONFIRMED_LOW_ADX: `470`
- REENTRIES_BLOCKED_BY_ADX: `1526`
- SIMULTANEOUS_BUY_SELL_SETUPS: `10`
- SELL_PRECEDENCE_EVENTS: `10`

Identity: `REENTRY_EVENTS = REENTRIES_CONFIRMED_LOW_ADX + REENTRIES_BLOCKED_BY_ADX`; `SELL_PRECEDENCE_EVENTS <= SIMULTANEOUS_BUY_SELL_SETUPS`. BUY_SIGNALS = confirmed re-entries minus simultaneous setups (SELL precedence).

## Signal / execution attribution

- BUY_SIGNALS: `460`
- SELL_SIGNALS: `32150`
- EXECUTED_BUYS: `403`
- EXECUTED_SELLS: `403`
- REJECTED_BUYS: `57`
- SELL_SIGNALS_WITHOUT_POSITION: `27936`

## Baseline behavior anchor

| Metric | expected (19B) | actual | match |
|---|---|---|---|
| closed_trades | 406 | 406 | True |
| net_pnl | -20.023554 | -20.023554 | True |
| profit_factor | 0.390291 | 0.390291 | True |
| expectancy | -0.049319 | -0.049319 | True |
| max_drawdown | 0.016775 | 0.016775 | True |

## Predeclared interpretation

IMPROVED iff expectancy, profit factor and net PnL improve while max drawdown does not worsen by more than `0.010000` absolute; NOT_IMPROVED when no metric improves or at least two of the three economic metrics deteriorate; otherwise MIXED. No composite score.

## Safety

- WALK_FORWARD_READS: `0`
- FINAL_HOLDOUT_READS: `0`
- FINAL_HOLDOUT_EXECUTIONS: `0`
- HOLDOUT_STATE: `PRISTINE`

Development may orient which candidate deserves to advance, but it does not demonstrate out-of-sample edge. EDGE_PRESENT and STRATEGY_PROMOTABLE remain NOT_EVALUATED.
