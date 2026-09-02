# Phase 16 Real Paper Baseline Runner Design

## Decision

Phase 16 will start with a 7-day real paper-trading stabilization run using the deterministic `EmaRsiBaseline` strategy before any LLM decisions are enabled.

After those 7 days, if the runner is operationally stable, the project will begin a new LLM paper run using Gemini. The LLM activation is explicitly out of scope for this baseline-runner implementation and must use a new strategy version/hash.

## Goals

- Run paper trading continuously on `lenovosrv` for 7 calendar days.
- Use real Bybit Production market data.
- Simulate execution locally with the existing `PaperEngine`.
- Keep `LIVE` disabled at all times.
- Persist enough evidence to support Phase 16 certification later.
- Produce periodic reports without fabricating trades or compressing time.

## Non-Goals

- No real-money trading.
- No Bybit LIVE order placement.
- No Testnet orders in this runner.
- No LLM decisions during the first 7 days.
- No artificial trades to satisfy the 200-trade threshold.
- No silent strategy changes during a certification run.

## Runtime Mode

The first runner will use:

```text
decision_source = baseline
strategy = EmaRsiBaseline
symbol = ETHUSDT
timeframe = 15m
runtime = Docker Compose service
restart_policy = unless-stopped
host = lenovosrv
```

The runner must be safe by default:

```text
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

If either value is unsafe, startup must fail before subscribing to market data.

## Architecture

Add a real-time paper runner as an application orchestration layer, not as new trading-domain logic.

```text
Bybit WebSocket
  -> market data normalization
  -> candle/feature state
  -> EmaRsiBaseline decision
  -> TradingDecision
  -> RiskEngine
  -> PaperEngine
  -> paper event/fill/equity snapshot
  -> PostgreSQL + report artifacts
```

The existing `PaperEngine` remains the execution simulator. It already enforces the correct order: open-position exits first, then Risk Engine approval, then simulated fills with fees and slippage.

## Components

### CLI

Create a command:

```bash
uv run python -m main paper-runner --symbols ETHUSDT --timeframe 15m
```

The command should support a bounded `--seconds` option for smoke tests and run indefinitely by default in Docker.

### Service

Create a service that owns the loop:

- connect to Bybit Production WebSocket;
- process only closed candles for the configured timeframe;
- call `EmaRsiBaseline.on_candle`;
- convert the signal to `TradingDecision`;
- call `PaperEngine.on_price`;
- persist every decision, rejection, fill, equity snapshot, and health event;
- generate/update periodic paper reports.

### Persistence

Use PostgreSQL for runtime records. The implementation may start with minimal tables if no existing schema fits exactly, but records must include:

- session id;
- strategy version;
- strategy hash;
- decision source;
- symbol;
- timeframe;
- timestamp;
- action;
- risk decision/reason;
- fill details when filled;
- fees;
- slippage;
- equity;
- kill switch state.

File artifacts remain the Phase 16 gate interface:

- `docs/phases/16/certification-state.json`;
- `docs/phases/16/PAPER_CERTIFICATION_REPORT.md`;
- `docs/phases/16/evidence/*.log`.

The certification checker must continue to read real observed evidence only.

## Certification Semantics

The 7-day baseline run does not complete Phase 16 by itself. Phase 16 remains `PENDING` until all real thresholds are met:

```text
calendar_days >= 30
trade_count >= 200
market_regimes >= 2
periodic_reports >= 1
strategy_hash unchanged
```

The 7-day baseline run contributes operational evidence and can become part of certification only for the baseline strategy. When Gemini is enabled on day 8, it must use a new strategy hash, so the Gemini certification window starts separately unless the user explicitly chooses to certify baseline only.

## Docker Deployment On lenovosrv

The Compose deployment should include:

- `postgres`;
- `paper-runner`;
- `prometheus`;
- `grafana`.

`paper-runner` should:

- use the project image;
- run as a non-root user when the image supports it;
- depend on PostgreSQL health;
- use `restart: unless-stopped`;
- receive configuration via environment variables or `.env` mounted/loaded by Compose;
- never copy `.envrc` or secrets into the image;
- persist data in Docker volumes or bind mounts under `/srv/docker/<service>/...` on `lenovosrv` when server deployment is applied.

No ports should be exposed publicly. Existing local-only bindings for Postgres, Prometheus, and Grafana should remain restricted unless the user explicitly approves LAN exposure and firewall changes.

## Configuration

`config/paper.yaml` should become the safe paper-mode profile:

```yaml
trading_mode: paper
live_trading_enabled: false
paper_decision_source: baseline
paper_symbols:
  - ETHUSDT
paper_timeframe: 15m
paper_report_interval_hours: 24
paper_max_runtime_days: 7
```

`.env.example` should document variable names only, without real secrets.

## Safety

- `LIVE_TRADING_ENABLED=true` must be rejected by the runner.
- The runner must not import or call Bybit private order-placement code.
- The LLM provider is not used in baseline mode.
- Risk sizing, stops, take profit, trailing stop, daily loss, max drawdown, max open positions, and kill switch remain controlled by deterministic code.
- On market stream failure, reconnect with backoff and record the health event.
- On persistence failure, stop or enter fail-safe mode rather than silently losing evidence.

## Reporting

The runner should produce periodic reports at least every 24 hours containing:

- uptime and gaps;
- number of candles processed;
- decisions by action;
- fills/trades;
- rejected decisions by risk reason;
- fees and slippage;
- realized/unrealized PnL;
- drawdown;
- kill switch state;
- current certification progress.

Reports are evidence artifacts, not marketing summaries. A losing result is valid evidence.

## Testing

Implementation should use TDD and include:

- unit tests for baseline signal to paper-event orchestration;
- tests that unsafe LIVE config fails startup;
- tests that no Bybit private order client is called;
- tests for reconnect/error handling boundaries;
- tests for periodic report generation from persisted records;
- a smoke test with `--seconds` for local and container execution.

Gate-relevant commands must be captured with `harness/scripts/evidence.sh`.

## Infra Gate

Any Docker Compose service changes, server deployment, image build, `docker compose up`, or server-side bind mounts require an infra/dependency proposal and explicit user approval before APPLY.

Pre-gate work may include design, plan, code, tests, `docker compose config`, and other read-only/dry-run validation. Actual server deployment to `lenovosrv` is post-approval only.

## Known Limitations

- The existing `paper-session` command runs deterministic sessions over frozen historical data. It is not the real-time runner.
- The existing `market-worker` ingests market data but does not execute paper decisions.
- The initial 7-day baseline run validates operational stability, not LLM economic value.
- Gemini paper trading starts a new strategy version/hash after the baseline stabilization period.
