# Phase 18D — DEVELOPMENT Economic Evaluation (three strategies)

- A baseline-v1: `2a9b4abda1ef24d1ef854c0614b8bc97e38d532860b9bccf228f806343e6db4e`
- B EmaRsiBtcContext-v1: `57ecf38f4f7e26355231414906375ea1b43d2e2a0d6ba2e3e773dff94789015f`
- C EmaRsiBtcRegime-v1: `02d4c0019fd735a24451f0b065e762c73423af9717097056dc20c122152184c9`
- Slice: DEVELOPMENT `[0, 62208)`
- Reproducibility: `PASS`
- Development result (C vs A): `MIXED`
- Incremental result (C vs B): `IMPROVED`
- Walk-forward candidate: `NO`
- Edge present: `NOT_EVALUATED_OUT_OF_SAMPLE`
- Strategy promotable: `NOT_EVALUATED`

| Metric | baseline-v1 | EmaRsiBtcContext-v1 | EmaRsiBtcRegime-v1 | Regime vs Baseline | Regime vs Context |
|---|---|---|---|---|---|
| signals_buy | 634 | 421 | 391 | -243.000000 | -30.000000 |
| signals_sell | 1021 | 1021 | 1021 | 0.000000 | 0.000000 |
| fills | 812 | 782 | 782 | -30.000000 | 0.000000 |
| closed_trades | 406 | 391 | 391 | -15.000000 | 0.000000 |
| net_pnl | -20.023554 | -20.000759 | -19.646087 | 0.377467 | 0.354672 |
| return_pct | -0.020024 | -0.020001 | -0.019646 | 0.000377 | 0.000355 |
| fees | 16.242716 | 15.641898 | 15.642253 | -0.600463 | 0.000355 |
| slippage | 3.248543 | 3.128380 | 3.128451 | -0.120093 | 0.000071 |
| max_drawdown | 0.016775 | 0.016872 | 0.016518 | -0.000257 | -0.000355 |
| profit_factor | 0.390291 | 0.402466 | 0.413466 | 0.023176 | 0.011000 |
| expectancy | -0.049319 | -0.051153 | -0.050246 | -0.000927 | 0.000907 |
| win_rate | 0.083744 | 0.084399 | 0.092072 | 0.008328 | 0.007673 |
| average_win | 0.376988 | 0.408224 | 0.384699 | 0.007710 | -0.023526 |
| average_loss | -0.088283 | -0.093498 | -0.094353 | -0.006070 | -0.000855 |

## Primary deltas (Regime vs Baseline)

- DELTA_NET_PNL: `0.377467`
- DELTA_RETURN_PCT: `0.000377`
- DELTA_MAX_DRAWDOWN: `-0.000257`
- DELTA_PROFIT_FACTOR: `0.023176`
- DELTA_EXPECTANCY: `-0.000927`
- DELTA_TRADES: `-15`
- DELTA_FEES: `-0.600463`
- DELTA_SLIPPAGE: `-0.120093`

## Secondary deltas (Regime vs Context)

- REGIME_VS_CONTEXT_DELTA_NET_PNL: `0.354672`
- REGIME_VS_CONTEXT_DELTA_PROFIT_FACTOR: `0.011000`
- REGIME_VS_CONTEXT_DELTA_EXPECTANCY: `0.000907`
- REGIME_VS_CONTEXT_DELTA_MAX_DRAWDOWN: `-0.000355`
- REGIME_VS_CONTEXT_DELTA_TRADES: `0`

## BTC filter attribution (descriptive)

- BASELINE_BUY_CANDIDATES: `634`
- CONTEXT_CONFIRMED_BUYS: `421`
- REGIME_CONFIRMED_BUYS: `391`
- REGIME_BLOCKED_BUYS: `243`
- ADDITIONAL_BUYS_BLOCKED_BY_SLOPE: `30`

Attribution is descriptive only. Blocking an entry changes the later portfolio path, so it is not a perfect counterfactual and no causal claim about blocked winners/losers is made.

## Predeclared interpretation

IMPROVED iff expectancy, profit factor and net PnL improve while max drawdown does not worsen by more than `0.010000` absolute; NOT_IMPROVED when no metric improves or at least two of the three economic metrics deteriorate; otherwise MIXED. No composite score.

## Safety

- WALK_FORWARD_READS: `0`
- FINAL_HOLDOUT_READS: `0`
- FINAL_HOLDOUT_EXECUTIONS: `0`
- HOLDOUT_STATE: `PRISTINE`

Development may orient which candidate deserves to advance, but it does not demonstrate out-of-sample edge. EDGE_PRESENT and STRATEGY_PROMOTABLE remain NOT_EVALUATED.
