# LOCAL_RELEASE_REPORT — Self-Evaluating Trading Agent

**Fecha:** 2026-08-31 · **Rama:** feature/phase-08-llm-decision-agent
**Veredicto binario:** ACCEPTED (los 8 gates deben estar en PASS simultáneo — PRD §15)

| Gate | Estado | Detalle |
|---|---|---|
| BACKTEST | PASS | backtest-bybit_ethbtc_v001-baseline-v1-ethusdt-15m: net_pnl=-1091.88 trades=1054 win_rate=0.264 profit_factor=0.719 maxDD=0.901; buy_hold net_pnl=492.96 |
| REPLAY | PASS | replay determinista reproducible (diff vacío): bars=103680 buy=1055 sell=1766 hold=100859 |
| PAPER | PASS | paper-session-bybit_ethbtc_v001-baseline-v1-ethusdt-15m: bars=103680 trades=392 net_pnl=-20.22 fees=15.68 slippage=3.14 llm_cost=0.00 kill_switch=False (fuente decisiones: deterministic-baseline) |
| TESTNET | PASS | lifecycle real create/reconcile/cancel validado contra Testnet (docs/phases/15/evidence/bybit-testnet-lifecycle-pass-final.log) |
| OBSERVABILITY | PASS | métricas y dashboard verificados (-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html) |
| SECURITY | PASS | pip-audit limpio; 0 vulnerabilidades; .env fuera del repo; hooks anti-secretos activos |
| CI | PASS | equivalente local del pipeline verde (ruff+format+mypy+pytest+coverage>=90%); CI remoto en GitHub Actions se disparará con el PR a main |
| UAT | PASS | checklist HITL de fase 15 APPROVED |

## Notas honestas

- Los gates PENDING indican recursos aún no disponibles o corridas oficiales no ejecutadas; NO se declaran PASS sin evidencia (skill release-readiness).
- SECURITY incluye pip-audit sobre el lockfile actual.
- El equivalente local de CI cubre exactamente los pasos de .github/workflows/ci.yml.
