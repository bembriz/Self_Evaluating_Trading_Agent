# Phase 18A Strategy Definition

## Identity

- Strategy name: `EmaRsiBtcContext`
- Strategy version: `ema-rsi-btc-context-v1`
- Strategy artifact identity: `f8a9b50b45059d99c1c68da40bc1abd237567717ba7999094ee4c306004be1db`
- Existing identity API: `lab.fingerprints.strategy_artifact_identity`
- Kind: `deterministic`
- LLM: none

Declared source bundle:

- `lab.strategies.ema_rsi_btc_context`
- `domain.trading.strategy`
- `domain.market.indicators`

Normalized configuration:

```json
{
  "btc_ema_fast": 20,
  "btc_ema_slow": 50,
  "ema_fast": 20,
  "ema_slow": 50,
  "rsi_exit": 80.0,
  "rsi_period": 14
}
```

## Decision Contract

`EmaRsiBaseline` remains the sole producer of ETH candidate signals. BTC context is
`BTC EMA20 > BTC EMA50` on the aligned confirmed 15m candle.

- ETH baseline BUY + BTC bullish: BUY / `ema_cross_up_btc_confirmed`.
- ETH baseline BUY + BTC bearish or BTC warmup: HOLD / `btc_context_block`.
- ETH baseline SELL: returned unchanged for every BTC state, including warmup.
- ETH baseline HOLD: returned unchanged for every BTC state, including warmup.
- BTC never creates BUY and never forces SELL.

The protected baseline file has Git blob `8bee0ae0ef2064e38d857e13c9862f5bc373b120`
at HEAD and has no Phase 18A diff.

## Evaluation Boundary

This evidence establishes implementation behavior only. `EDGE_PRESENT` and
`STRATEGY_PROMOTABLE` are `NOT_EVALUATED`.
