# Phase 18B — DEVELOPMENT Economic Evaluation

- Strategy A: `baseline-v1` (spec `2a9b4abda1ef24d1ef854c0614b8bc97e38d532860b9bccf228f806343e6db4e`)
- Strategy B: `EmaRsiBtcContext-v1` (spec `57ecf38f4f7e26355231414906375ea1b43d2e2a0d6ba2e3e773dff94789015f`)
- Slice: DEVELOPMENT `[0, 62208)` (ETHUSDT 15m, BTCUSDT 15m context only for B)
- SpecIds differ: `True`
- Reproducibility: `PASS`
- Development result: `MIXED`
- Walk-forward candidate: `NO`
- Edge present: `NOT_EVALUATED_OUT_OF_SAMPLE`
- Strategy promotable: `NOT_EVALUATED`

| Metric | baseline-v1 | EmaRsiBtcContext-v1 | delta |
|---|---|---|---|
| signals_buy | 634 | 421 | -213.000000 |
| signals_sell | 1021 | 1021 | 0.000000 |
| fills | 812 | 782 | -30.000000 |
| closed_trades | 406 | 391 | -15.000000 |
| net_pnl | -20.023554 | -20.000759 | 0.022795 |
| return_pct | -0.020024 | -0.020001 | 0.000023 |
| fees | 16.242716 | 15.641898 | -0.600818 |
| slippage | 3.248543 | 3.128380 | -0.120164 |
| max_drawdown | 0.016775 | 0.016872 | 0.000097 |
| profit_factor | 0.390291 | 0.402466 | 0.012175 |
| expectancy | -0.049319 | -0.051153 | -0.001834 |
| win_rate | 0.083744 | 0.084399 | 0.000655 |
| average_win | 0.376988 | 0.408224 | 0.031236 |
| average_loss | -0.088283 | -0.093498 | -0.005215 |

## BTC filter attribution

- baseline_buy_candidates: `634`
- btc_confirmed_buys: `421`
- btc_blocked_buys: `213`
- blocked baseline trades: `137`
- blocked baseline winners: `11`
- blocked baseline losers: `126`
- blocked baseline flats: `0`
- blocked baseline net PnL: `-5.403646`
- blocked baseline avg net PnL: `-0.039443`
- trade reduction: `3.694581%`

## Predeclared interpretation

IMPROVED requires expectancy, profit factor and net PnL to improve while max drawdown does not worsen by more than `0.010000` absolute; NOT_IMPROVED when no metric improves or at least two of the three economic metrics deteriorate; otherwise MIXED. No composite score.

## Safety

- WALK_FORWARD_READS: `0`
- FINAL_HOLDOUT_READS: `0`
- FINAL_HOLDOUT_EXECUTIONS: `0`
- HOLDOUT_STATE: `PRISTINE`

Development may orient which candidate deserves to advance, but it does not demonstrate out-of-sample edge. EDGE_PRESENT and STRATEGY_PROMOTABLE remain NOT_EVALUATED.
