# Phase 18A Alignment And Causality Evidence

## Dataset

- Dataset id: `BYBIT_ETHBTC_V001`
- Manifest SHA-256: `3c008c3ab5299e33beaa61c80ddc927d2f14fc3f96924b5d6db537b2a4e91644`
- ETHUSDT 15m SHA-256: `f561207c018d0f4ade1afdaca3d349a53faec49d732bb5f50933db64e2cbb31d`
- BTCUSDT 15m SHA-256: `ef39b08dcca27438592141ca3a2233165f016ebcb3bc063235df0e00c9809f52`
- Manifest row count per 15m symbol: `103680`

## Development Smoke Range

- Primary: ETHUSDT 15m `[0, 5000)`
- Context: BTCUSDT 15m `[0, 5000)`
- Rows compared: `5000`
- First timestamp: `1694195100000`
- Last timestamp: `1698694200000`
- Exact timestamp equality at every index: `PASS`
- Timeframe equality: `PASS`
- Dataset/range equality: `PASS`

The candidate validates non-empty equal lengths and exact timestamp equality before
execution. `from_adapters` additionally validates primary/context symbols, 15m timeframe,
dataset identity, manifest identity, and row bounds. The unchanged `LabSessionRunner` ETH
candle is checked against the exact next preloaded ETH candle before each decision.

## No Lookahead

BTC EMA20 and EMA50 reuse `domain.market.indicators.ema`. At index `i`, that function
depends only on closes `0..i`. Context remains unavailable until both EMA values exist.
The temporal-corruption unit test changes BTC candles strictly after T and verifies that
all candidate decisions through T remain identical.

- Forward fill: none
- Interpolation: none
- Synthetic candles: none
- Nearest timestamp matching: none
- Future BTC access for context at T: none
- NO_LOOKAHEAD: `PASS`

## Holdout Safety

- Requested FINAL_HOLDOUT ranges: `0`
- FINAL_HOLDOUT executions: `0`
- Walk-forward executions: `0`
- Holdout state: `PRISTINE`

The smoke records both adapter range requests and derives its holdout-read counter from
those observations. The requests are ETHUSDT `[0, 5000)` and BTCUSDT `[0, 5000)`, both
wholly inside DEVELOPMENT `[0, 62208)`. E2E independently records the same requested
ranges and asserts zero intersection with FINAL_HOLDOUT.
