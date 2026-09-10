# DP-004 — Paper Runner Container Deployment

> **DECISIÓN DEL USUARIO: ✅ APPROVED** — 2026-09-01 (sesión OpenCode). Aprobado explícitamente vía selector. Autoriza: clonar/transferir código, `docker build`, `docker compose up -d postgres paper-runner`, bind-mounts bajo `/srv/docker/self-evaluating-trading-agent/` y migración Alembic 0008 en lenovosrv.

## Necesidad

Run Phase 16 baseline paper trading for 7 calendar days on `lenovosrv` using Docker Compose with `restart: unless-stopped`.

## Cambios Solicitados

- Add Compose service `paper-runner`.
- Build/use the existing project image.
- Run `python -m main paper-runner --symbols ETHUSDT --timeframe 15m`.
- Keep `LIVE_TRADING_ENABLED=false`.
- Use existing `postgres`, `prometheus`, and `grafana` services.
- Deploy under `/srv/docker/self-evaluating-trading-agent/...` on `lenovosrv` during APPLY.

## Seguridad

- No `.envrc` copied into image.
- No LIVE trading.
- No Bybit private order client used.
- No public port exposure added.
- Secrets remain environment variables only.

## Pre-Gate Validation

- `docker compose config` only.
- No `docker build`, `docker pull`, `docker compose up`, remote bind mounts, or firewall changes before APPROVED.

## Rollback

- Stop service with `docker compose stop paper-runner`.
- Remove service definition in a reverting change.
- Preserve PostgreSQL volume and evidence artifacts unless user explicitly authorizes deletion.

## Aclaración De Estado Actual

Local `postgres` was started only after explicit user approval to unblock integration tests. No `paper-runner` service, server deployment, image build, remote bind mounts, or firewall changes are authorized until DP-004 receives explicit APPROVED.
