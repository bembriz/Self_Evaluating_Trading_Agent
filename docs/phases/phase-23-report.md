# Reporte de Fase 23 — Medallion Market Data & Trade-Level Replay

**Fecha:** 2026-09-29
**Estado de fase:** in_progress
**Avance fase:** 90.0% (12/13 entregables; tope 90% sin gate) · **Avance global:** 85.4%
**Gate:** pending

---

## 1. Executive Summary

La Fase 23 construyó el pipeline **Medallion** de market data de Bybit Spot (Bronze idempotente → Silver trades canónicos → Silver candles multi-timeframe → Gold replay dataset inmutable), un **motor de Trade-Level Replay de dos relojes** (decisión a cierre de vela confirmada + ejecución contra la secuencia real de trades), su **despliegue aislado en lenovosrv** y la **re-ejecución de las 3 estrategias congeladas** (baseline/donchian/bollinger) comparando el modelo OLD (close-only) vs NEW (trade-sequence) sobre 647 días DEVELOPMENT. Todo se realizó sin leer walk-forward ni holdout, manteniendo intactas la certificación paper y GastosIA. M10 (UAT + auditoría + candidato de integración) queda preparado con cobertura `src` 90.56%, lint/typing verdes y auditoría final PASS.

## 2. Objetivo

Diseñar y construir una capa de datos de mercado (Medallion) y un motor de replay fiel a nivel de trade que permita comparar estrategias existentes con mayor fidelidad de ejecución, como base de validación del producto (PRD §25, §29, §40-45; ADR-0005/0006/0007).

## 3. Scope

- **M0** Arquitectura, gobernanza, skills y diseño de storage/plataforma.
- **M0-I** Revalidación read-only de infraestructura lenovosrv.
- **M0-II** Backup de GastosIA + test de restore aislado.
- **M1** Reformateo HDD + mount `/srv/data` (gate destructivo aprobado).
- **M2** Fundación de directorios/red de plataforma.
- **M3** Ingesta Bronze idempotente (trades Bybit Spot).
- **M4** Silver trades canónicos deterministas.
- **M5** Silver candles multi-timeframe deterministas.
- **M6** Gold replay dataset inmutable (manifiesto).
- **M7** Motor de Trade-Level Replay (dos relojes, trigger/fill).
- **M8** Despliegue Medallion en lenovosrv (contenedor one-shot aislado).
- **M9** Re-ejecución de estrategias existentes (OLD vs NEW, DEVELOPMENT).
- **M10** UAT + auditoría final + candidato de integración a `main`.

## 4. Out of Scope

- Order-book replay histórico (§148 de la arquitectura).
- Walk-forward y final holdout (no se leen ni ejecutan: `*_READS=0`).
- Conclusión de rentabilidad o viabilidad OOS (`OOS_CONCLUSION=NO`).
- Migración del runtime de paper/certificación (intocable).
- Automatización/servicios daemon de Medallion (one-shot/batch únicamente).

## 5. Arquitectura antes/después

- **Antes:** dataset congelado `BYBIT_ETHBTC_V001` + `backtest_engine` event-driven sobre velas; replay de un solo reloj (decisión y fill a `candle.close`); datos históricos vía `historical_data.py`.
- **Después:** nueva capa `src/infrastructure/medallion` (bronze, silver trades, candles, gold, replay, split_guard, strategy_provider + CLIs), tiering NVMe/HDD (`/srv/data` canónico, `/srv/fast` scratch), replay de **dos relojes** con fill contra secuencia real de trades. Aditivo: no reemplaza rutas existentes del producto. Ver `docs/design/medallion-replay-architecture.md` y ADR-0005/0006/0007.

## 6. Archivos creados

- **`src/infrastructure/medallion/`** (14): `__init__, bronze, candles, candles_cli, cli, gold, gold_cli, replay, replay_cli, schema_backfill_cli, silver, silver_cli, split_guard, strategy_provider`.
- **Tests** (8): `test_bronze_ingest, test_gold_dataset, test_silver_candles, test_silver_trades, test_source_schema, test_strategy_provider, test_strategy_replay_no_lookahead, test_trade_replay`.
- **`harness/scripts/m9b_common_window.py`** + `harness/tests/test_m9b_common_window.py`.
- **`deployment/medallion/`** (4): `Dockerfile, Dockerfile.dockerignore, compose.yaml, README.md`.
- **`deployment/platform/`** (2): `compose.yaml, README.md`.
- **ADR** (3): `ADR-0005-two-clock-replay`, `ADR-0006-shared-platform-lenovosrv`, `ADR-0007-storage-tiering`.
- **Skill** (1): `.opencode/skills/medallion-market-data/SKILL.md`.
- Documentación/evidencia: `docs/design/medallion-replay-architecture.md`, `docs/phases/23/**`, `docs/uat/phase-23-uat.md`.

## 7. Archivos modificados

- `.opencode/skills/backtesting/SKILL.md`, `.opencode/skills/bybit-integration/SKILL.md` (replay dos relojes; archivos históricos Bybit).
- `AGENTS.md` (routing Medallion/replay/plataforma), `docs/skill-gap/SKILL_GAP.md`.
- `harness/state/progress.yaml` (estado de la fase, vía `progress.py`).

## 8. Dependencias

**Ninguna nueva.** Cero cambios en `pyproject.toml` / `uv.lock`. Los CLIs Medallion y el runner son **stdlib puro**; la imagen usa la base ya declarada `python:3.12-slim` (pull aprobado en M8, gate de dependencia en sesión).

## 9. Configuración

Sin cambios en `config/*.yaml` ni `.env.example`. Los guards declarativos `WALK_FORWARD_READS=0` / `FINAL_HOLDOUT_READS=0` viven en `deployment/medallion/compose.yaml`. Marker de volumen: `/srv/data/.lenovosrv-data-volume`.

## 10. Comandos exactos

```bash
# Cobertura autoritativa M10 (src, branch)
uv run pytest tests --ignore=tests/integration -o addopts= -q \
  --cov=src --cov-branch \
  --cov-report=json:docs/phases/23/evidence/coverage.json --cov-fail-under=90

# Cobertura complementaria medallion
uv run pytest tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py \
  tests/test_gold_dataset.py tests/test_source_schema.py tests/test_trade_replay.py \
  tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py \
  -o addopts= -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90

# Calidad
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests

# Auditoría final (read-only, local + lenovosrv)
bash /tmp/opencode/m10-final-audit.sh
```

(Comandos completos de M0–M9 en `docs/phases/23/evidence/log.md`.)

## 11. Rutas

- Canónico HDD `/srv/data/medallion/{bronze,silver,gold}` (+ marker `/srv/data/.lenovosrv-data-volume`).
- Scratch/caché NVMe `/srv/fast/medallion/{replay-work,m9b-full,uat}`, desechable.
- Deploy `/srv/docker/medallion/` (espejo del repo).
- Repo: `src/infrastructure/medallion`, `harness/scripts/m9b_common_window.py`, `deployment/medallion`.

## 12. API endpoints

No aplica. Fase de datos/infra sin cambios en FastAPI.

## 13. Migraciones

No aplica. Sin cambios en `migrations/`.

## 14. Tests

| Nivel | Ejecutado | Resultado | Evidencia |
|---|---|---|---|
| Unit | ☑ | PASS | `coverage-src.log` (1263 passed, 1 skipped); `m9b2b-03-tests-medallion.log` (323 passed) |
| Integration | ☑ | PASS | M7/M8 replay + M9 full DEVELOPMENT (`m9b-full-03-verify.log`) |
| E2E | ☑ | PASS | cadena market→replay→comparación (M9) + suite global |

## 15. Coverage

- `src` (branch): **90.56%** ≥ 90 (`docs/phases/23/evidence/coverage.json`, M10).
- `src/infrastructure/medallion` (branch): **94.27%** (`m9b2b-03-tests-medallion.log`), complementaria.

## 16. E2E

- M7: replay determinista (RUN1 `created` → RUN2 byte-idéntico → RUN3 `skipped`), sin lookahead.
- M8: mismo escenario scripted en contenedor aislado; ledger byte-idéntico a M7 (`6d64b62b…`).
- M9: 6 corridas OLD/NEW sobre 647 días; paridad `signal_hash`/`candle_hash` OLD==NEW en las 3 estrategias.

## 17. UAT

- Checklist: `docs/uat/phase-23-uat.md` (9 pasos: Bronze idempotente, Silver/candles deterministas, Gold inmutable, replay dos relojes/no-lookahead, M9 OLD vs NEW, aislamiento M8, marker negativo FAIL CLOSED, paper/certificación intactos).
- Veredicto: **APPROVED** (usuario, 2026-09-29; 9/9 PASS). Incidencias I-1/I-2 de harness documentadas y corregidas; sin fallos de producto.

## 18. Evidencias

Índice completo en `docs/phases/23/evidence/log.md` (M0–M9). Evidencia M10: `coverage.json`, `coverage-src.log`, `lint.log`, `typing.log`, `m10-final-audit.log`, `m10-integration-candidate.md`, `docs/uat/phase-23-uat.md`.

## 19. Métricas

- Dataset full DEVELOPMENT: 647 días, **62112 velas 15m**; dataset 3 días: `gold-replay-a8c49e0b…`.
- Replay M7/M8: `decisions_total=45, filled=23, dropped=22, closed=23, trades=1 880 793`; ledger sha `6d64b62b…`.
- M9 (net realized, in-sample): baseline OLD −22.812989 / NEW −24.864136; donchian −27.741589 / −38.777176; bollinger −16.936591 / −18.183960.
- Cobertura: src 90.56%; medallion 94.27%.

## 20. Logs relevantes

`m3-06-uat-run2-idempotent.log` (SKIP bronze), `m5-07-uat-run2-determinism.log`, `m6-06-uat-run2-determinism.log`, `m7-07-uat-verify.log`, `m8-07-uat-replay.log`, `m9b-full-03-verify.log`, `m9b-review-consistency.log`, `m10-final-audit.log`.

## 21. Git diff

`git diff --shortstat main...HEAD` → **402 files changed, 42273 insertions(+), 4 deletions(-)**. Detalle y blast radius en `docs/phases/23/m10-integration-candidate.md`.

## 22. Riesgos

| Riesgo | Severidad | Mitigación |
|---|---|---|
| Replay nuevo (641 stmts) | media | 91% branch; determinismo byte-a-byte; no-lookahead testeado |
| Estrategias reales integradas (M9) | media | `DEVELOPMENT_ONLY=YES`, `OOS_CONCLUSION=NO`, WF/holdout no leídos |
| Migración destructiva HDD (M1) | alta (histórica) | Ejecutada con gate + backup/restore GastosIA; irreversible pero cerrada |
| Volumen de docs/evidencia | baja | No afecta runtime |

## 23. Seguridad

- Secret scan `main...HEAD`: **0 hits** (private key, AWS, credenciales literal, Bearer, URL creds) + hex-64 en `.py` = 0; sin `.env/.pem/.key/id_rsa/.p12`.
- Contenedor M8: `network_mode: none`, `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, `USER 1000:1000`, canónico `ro`, marker `ro`, sin puertos/credenciales/PG.
- Paper/certificación intactos; `HOLDOUT_STATE=PRISTINE`; `WALK_FORWARD_READS=0`.

## 24. Deuda técnica

Ninguna nueva declarada en la fase.

## 25. Known Issues

- El replay de M9 en las 3 corridas resultó con net realizado negativo; se documenta explícitamente como resultado **in-sample DEVELOPMENT**, sin conclusión de rentabilidad.
- No se ejecutó una segunda corrida completa de 647 días para contraste de determinismo a esa escala (solo smoke de 3 días + garantía por diseño/diseño de hash).

## 26. Rollback

- Runtime: no hay daemon/servicio Medallion que revertir (contenedor one-shot efímero).
- Datos: canónico `/srv/data` no se modifica en operaciones de replay; scratch `/srv/fast/medallion/**` es desechable.
- Repo: revertir la rama `medalion` (18 commits) o no integrar a `main` (integración es fast-forward pendiente de gate).

## 27. Competencias de Ingeniería de Software practicadas

Data Engineering (pipeline Medallion, idempotencia, particionado), Testing (unit/integration/E2E, cobertura branch), Bases de datos/datos (inmutabilidad, manifiestos con hash), Arquitectura hexagonal (adapters de infraestructura), Docker (imagen fail-closed, aislamiento), SRE/Infra (tiering NVMe/HDD, backup/restore, gates destructivos), Security (secret scan, sin secretos), Observabilidad (ops logs), Async/lotes (runs secuenciales), Experimentación (OLD vs NEW), Git (commits atómicos, gobernanza).

## 28. Definition of Done

- [x] Scope completo (12/13; M10 en preparación)
- [x] Tests PASS (unit/integration/E2E)
- [x] Coverage ≥ 90% (src 90.56%)
- [x] Lint green / typing green
- [x] Documentación y evidencia completas
- [x] UAT aprobado (APPROVED, usuario, 2026-09-29)
- [ ] Aprobación de usuario / gate (PENDIENTE)
- [ ] CI (ver §29)

## 29. Estado CI

No hay pipeline remoto ejecutado para esta fase en el momento del reporte; calidad verificada localmente (ruff + format + mypy + suite completa). El repo tiene remoto `origin` pero el push/merge está sujeto a autorización explícita.

## 30. Solicitud de aprobación

- [ ] Presentado al usuario
- **DECISIÓN DEL USUARIO:** ☐ APPROVED ☐ REJECTED
- Comentario:
