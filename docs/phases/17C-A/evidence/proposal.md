# FASE 17C-A — Split Candidate Proposal (BYBIT_ETHBTC_V001 · ETHUSDT 15m)

> Proposal only. No strategy, no backtest, no replay, no trading metrics.
> No holdout analysis. Nothing frozen (`splits/v1.json` untouched, no HoldoutEpoch).

- Base: `fc1aaba` (HEAD == base; verified)
- Manifest: `docs/datasets/BYBIT_ETHBTC_V001.manifest.json`
  `sha256=3c008c3ab5299e33beaa61c80ddc927d2f14fc3f96924b5d6db537b2a4e91644`
- CSV verified: `datasets/BYBIT_ETHBTC_V001/ETHUSDT_15m.csv`
  `sha256=f561207c018d0f4ade1afdaca3d349a53faec49d732bb5f50933db64e2cbb31d` (matches manifest),
  103680 data rows, `start_ms=1694195100000`, `end_ms=1787506200000`.
- Rule: **60 / 25 / 15**, temporal, contiguous, `[start, end)`, day-aligned
  (all boundaries are multiples of 96 rows = full days).
- Artifact: `splits/CANDIDATE.json`

## DEVELOPMENT

- rows: 62208 (range [0, 62208))
- fechas: 2023-09-08T17:45:00+00:00 → 2025-06-17T17:30:00+00:00
- duración: 648.0 días (~21.3 meses)
- porcentaje: 60.0%

## WALK_FORWARD

- rows: 25920 (range [62208, 88128))
- fechas: 2025-06-17T17:45:00+00:00 → 2026-03-14T17:30:00+00:00
- duración: 270.0 días (~8.9 meses)
- porcentaje: 25.0%

## FINAL_HOLDOUT

- rows: 15552 (range [88128, 103680))
- fechas: 2026-03-14T17:45:00+00:00 → 2026-08-23T17:30:00+00:00
- duración: 162.0 días (~5.3 meses, al final temporal, intacto)
- porcentaje: 15.0%

## Justification

Simple distribution, not over-optimized: ~21 months of development data for
strategy development/backtesting, ~9 months of walk-forward for out-of-sample
validation, and ~5.3 months of final holdout at the temporal end for a single
unbiased estimate. Full-day-aligned boundaries avoid partial-day edge effects.

## Validations (tests/test_split_candidate_17c_a.py — 11 passed)

- TOTAL_ROWS = 62208 + 25920 + 15552 = 103680 ✔
- NO_OVERLAP=YES · NO_GAPS=YES · TEMPORAL_ORDER=YES ✔
- Final holdout ends at last row; timestamps match CSV; 15m contiguity at seams ✔
- Deterministic rebuild from manifest+CSV == CANDIDATE.json ✔
- Invalid ranges (gap / overlap / truncation / bad count) fail ✔

## Protected runtime

`git diff fc1aaba -- src/` empty → CLEAN (paper_runner, paper_engine, risk,
portfolio, strategy untouched).

---

SPLIT_CANDIDATE_READY
WAITING_FOR_HUMAN_SPLIT_FREEZE_GATE
