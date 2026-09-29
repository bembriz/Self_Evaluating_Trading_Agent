# UAT — Fase 23: Medallion Market Data & Trade-Level Replay

> Prueba de aceptación de usuario (HITL). El agente NO puede aprobar UAT.
> Ejecuta los pasos tal cual y completa "Resultado observado" y el veredicto final.
>
> **Alcance:** verifica la cadena Medallion (Bronze→Silver→Gold), el motor de
> Trade-Level Replay de dos relojes, su despliegue aislado en lenovosrv (M8) y la
> comparación OLD vs NEW en DEVELOPMENT (M9). **No** se ejecuta nada destructivo ni
> se toca walk-forward/holdout/paper/certificación.

## Precondiciones

> Estado requerido del entorno antes de empezar (servicios, datos, versión).

| # | Precondición | Verificada ☐ |
|---|---|---|
| 1 | Repo en rama `medalion`, `git rev-parse HEAD` = `a26f3eaa804af4266f60483a9b21f20a01d5c2a4` | ☐ |
| 2 | `uv` disponible y `uv run python -c "print('ok')"` funciona en el repo | ☐ |
| 3 | Acceso SSH sin contraseña: `ssh administrador@192.168.100.24 hostname` → `lenovosrv` | ☐ |
| 4 | Imagen Medallion presente: `docker image inspect seta-medallion:m8-79b1de5b8fc8` (en lenovosrv) | ☐ |
| 5 | Marker válido: `/srv/data/.lenovosrv-data-volume` contiene `LENOVO_DATA` | ☐ |
| 6 | Canónico presente: `/srv/data/medallion/{bronze,silver,gold}` y `/srv/fast/medallion/m9b-full/` | ☐ |
| 7 | `paper-runner` en ejecución (no se reinicia ni se toca) | ☐ |

## Entradas / Datos

> Datos, comandos o fixtures que necesitarás.

- **Dataset DEVELOPMENT (M8/M7):** `gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`
  (manifest sha256 `9411a4e01a5adccbb448df062f0eca857213e8259441535b5812ee4688af99df`), fechas `2024-06-01..03`.
- **Dataset full DEVELOPMENT (M9):** `gold-replay-5ca68f44c37d2321f56a10ecbc08bc0584d70c17826f07604dbba77a8b71134a`
  (manifest sha256 `c095d5740d9ca0c414ac0b11049008aa716262870edbeadc344dbb16188eb62e`), 647 días / 62112 velas 15m.
- **Ledger legacy M7/M8:** sha256 `6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625`.
- Artefactos M9 en lenovosrv: `/srv/fast/medallion/m9b-full/{strategy}-{model}-{summary.json,trades.jsonl}`.
- Imagen: `seta-medallion:m8-79b1de5b8fc8` (digest `sha256:df82686bfd6d…`).

## Pasos

> Convención: los pasos **L** se ejecutan en el repo local; los pasos **S** desde una
> sesión SSH a lenovosrv (`ssh administrador@192.168.100.24`). El canónico `/srv/data`
> se monta **read-only**; la escritura de scratch va a `/srv/fast/medallion/uat/` (NVMe, desechable).

### Paso 1 (L) — Suite automatizada de la fase (determinismo / idempotencia / no-lookahead)

```bash
uv run pytest tests/test_bronze_ingest.py tests/test_silver_trades.py tests/test_silver_candles.py \
  tests/test_gold_dataset.py tests/test_split_candidate_17c_a.py tests/test_trade_replay.py \
  tests/test_cli_replay.py tests/test_strategy_provider.py tests/test_strategy_replay_no_lookahead.py \
  -o addopts= -q --cov=infrastructure.medallion --cov-branch --cov-fail-under=90
```

**Resultado esperado:** todos los tests `passed` (≥323) y `Required test coverage of 90% reached`
(≈94%).

### Paso 2 (S) — Bronze idempotente (re-ingesta de días ya presentes ⇒ SKIP)

```bash
docker run --rm --network none --user 0:0 \
  -v /srv/data/medallion:/srv/data/medallion \
  -v /srv/data/.lenovosrv-data-volume:/srv/data/.lenovosrv-data-volume:ro \
  --entrypoint python3 seta-medallion:m8-79b1de5b8fc8 \
  -m infrastructure.medallion.cli \
  --dest-dir /srv/data/medallion/bronze/bybit/spot/ETHUSDT \
  --dates 2024-06-01,2024-06-02,2024-06-03 \
  --require-marker /srv/data/.lenovosrv-data-volume
```

**Resultado esperado:** 3 líneas `SKIPPED ETHUSDT_2024-06-0X.csv.gz sha256=…` con los mismos
hashes y `SUMMARY downloaded=0 skipped=3 total=3`. (Se añaden eventos `skipped` al ops-log;
no se reescriben los `.csv.gz`.)

### Paso 3 (S) — Silver trades determinista (scratch fresco + comparación con canónico)

```bash
rm -rf /srv/fast/medallion/uat/silver-trades
docker run --rm --network none --user 0:0 \
  -v /srv/data/medallion:/srv/data/medallion:ro \
  -v /srv/fast/medallion:/srv/fast/medallion \
  -v /srv/data/.lenovosrv-data-volume:/srv/data/.lenovosrv-data-volume:ro \
  --entrypoint python3 seta-medallion:m8-79b1de5b8fc8 \
  -m infrastructure.medallion.silver_cli \
  --bronze-dir /srv/data/medallion/bronze/bybit/spot/ETHUSDT \
  --dest-dir /srv/fast/medallion/uat/silver-trades \
  --dates 2024-06-01,2024-06-02,2024-06-03 \
  --require-marker /srv/data/.lenovosrv-data-volume
```

**Resultado esperado:** `SUMMARY transformed=3 skipped=0 total=3` y sha256 de cada salida
**idéntico** al canónico. Comparación:

```bash
for d in 2024-06-01 2024-06-02 2024-06-03; do
  a=$(sha256sum /srv/data/medallion/silver/trades/ETHUSDT/date=$d/*.csv.gz | awk '{print $1}')
  b=$(sha256sum /srv/fast/medallion/uat/silver-trades/date=$d/*.csv.gz | awk '{print $1}')
  [ "$a" = "$b" ] && echo "$d MATCH" || echo "$d DIFF"
done
```
→ 3 × `MATCH`.

### Paso 4 (S) — Candles deterministas (scratch fresco + comparación con canónico)

```bash
rm -rf /srv/fast/medallion/uat/silver-candles
docker run --rm --network none --user 0:0 \
  -v /srv/data/medallion:/srv/data/medallion:ro \
  -v /srv/fast/medallion:/srv/fast/medallion \
  -v /srv/data/.lenovosrv-data-volume:/srv/data/.lenovosrv-data-volume:ro \
  --entrypoint python3 seta-medallion:m8-79b1de5b8fc8 \
  -m infrastructure.medallion.candles_cli \
  --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \
  --dest-dir /srv/fast/medallion/uat/silver-candles \
  --dates 2024-06-01,2024-06-02,2024-06-03 \
  --require-marker /srv/data/.lenovosrv-data-volume
```

**Resultado esperado:** `SUMMARY transformed=21 skipped=0 total=21` (7 timeframes × 3 días) y
sha256 por timeframe **idéntico** al canónico (p. ej. 15m 2024-06-01 = `42c787578e7e…`).
Comparación análoga al paso 3 sobre `/srv/data/medallion/silver/candles/ETHUSDT`.

### Paso 5 (S) — Gold inmutable / determinista (dataset_id y manifest reproducibles)

```bash
rm -rf /srv/fast/medallion/uat/gold
docker run --rm --network none --user 0:0 \
  -v /srv/data/medallion:/srv/data/medallion:ro \
  -v /srv/fast/medallion:/srv/fast/medallion \
  -v /srv/data/.lenovosrv-data-volume:/srv/data/.lenovosrv-data-volume:ro \
  --entrypoint python3 seta-medallion:m8-79b1de5b8fc8 \
  -m infrastructure.medallion.gold_cli \
  --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \
  --candles-dir /srv/data/medallion/silver/candles/ETHUSDT \
  --dest-dir /srv/fast/medallion/uat/gold \
  --dates 2024-06-01,2024-06-02,2024-06-03 \
  --require-marker /srv/data/.lenovosrv-data-volume
```

**Resultado esperado:** `CREATED dataset_id=gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3`
y `manifest_sha256=9411a4e01a5adccbb448df062f0eca857213e8259441535b5812ee4688af99df`
(iguales al canónico ⇒ Gold reproducible). El canónico permanece intacto (`:ro`).

### Paso 6 (S) — Replay de dos relojes: determinismo byte-a-byte y no-lookahead

```bash
rm -rf /srv/fast/medallion/replay-work/uat-replay
docker run --rm --network none \
  -v /srv/data/medallion:/srv/data/medallion:ro \
  -v /srv/fast/medallion:/srv/fast/medallion \
  -v /srv/data/.lenovosrv-data-volume:/srv/data/.lenovosrv-data-volume:ro \
  --entrypoint python3 seta-medallion:m8-79b1de5b8fc8 \
  -m infrastructure.medallion.replay_cli \
  --dataset-dir /srv/data/medallion/gold/replay-datasets/ETHUSDT/gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3 \
  --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \
  --candles-dir /srv/data/medallion/silver/candles/ETHUSDT \
  --ledger-path /srv/fast/medallion/replay-work/uat-replay/ledger.jsonl \
  --require-marker /srv/data/.lenovosrv-data-volume
sha256sum /srv/fast/medallion/replay-work/uat-replay/ledger.jsonl
```

**Resultado esperado:** `STATUS=created … ledger_sha256=6d64b62b48575bdbcd…` y
`SUMMARY … closed_trades=23 trades=1880793`; el `sha256sum` del fichero =
`6d64b62b48575bdbcda19eb0dbbc46d53a7351606eb5fd93a9c038643a83e625` (idéntico a M7/M8 ⇒
replay determinista). Repite el `docker run` una segunda vez → `STATUS=skipped` (idempotente).
La ausencia de lookahead (solo velas confirmadas + primer trade elegible) está cubierta por
`tests/test_strategy_replay_no_lookahead.py` y `tests/test_trade_replay.py` (paso 1).

### Paso 7 (S) — M9: OLD (close-only) vs NEW (trade-sequence) en DEVELOPMENT

```bash
python3 - <<'PY'
import json, pathlib
d = pathlib.Path("/srv/fast/medallion/m9b-full")
for strat in ("baseline", "donchian", "bollinger"):
    rows = {}
    for model in ("old_close_only", "trade_sequence"):
        s = json.loads((d / f"{strat}-{model}-summary.json").read_text())
        rows[model] = s
    o, n = rows["old_close_only"], rows["trade_sequence"]
    print(strat, "signal_hash_match", o["signal_hash"] == n["signal_hash"],
          "candle_hash_match", o["candle_hash"] == n["candle_hash"],
          "net_old", round(o["metrics"]["net_pnl"], 6), "net_new", round(n["metrics"]["net_pnl"], 6))
PY
```

**Resultado esperado:** para las 3 estrategias `signal_hash_match True` y `candle_hash_match True`;
`net` OLD/NEW = baseline `-22.812989/-24.864136`, donchian `-27.741589/-38.777176`,
bollinger `-16.936591/-18.183960` (coinciden con `m9b-review.md`). Net negativo en las 6
combinaciones: es **in-sample DEVELOPMENT**, sin conclusión de rentabilidad.

### Paso 8 (S) — Aislamiento M8 (imagen/compose) + marker negativo FAIL CLOSED

```bash
# 8a. Aislamiento declarado (sin red, sin puertos, usuario no-root, mounts ro canónico)
docker image inspect seta-medallion:m8-79b1de5b8fc8 \
  --format 'User={{.Config.User}} Revision={{index .Config.Labels "org.opencontainers.image.revision"}}'

# 8b. Marker negativo ⇒ debe fallar ANTES de escribir
docker run --rm --network none \
  -v /srv/data/medallion:/srv/data/medallion:ro \
  -v /srv/data/.lenovosrv-data-volume:/srv/data/.lenovosrv-data-volume:ro \
  --entrypoint python3 seta-medallion:m8-79b1de5b8fc8 \
  -m infrastructure.medallion.replay_cli \
  --dataset-dir /srv/data/medallion/gold/replay-datasets/ETHUSDT/gold-replay-a8c49e0be9154194841a97c4f26225a76cef9fba8d9a6d080198359c124ebdc3 \
  --trades-dir /srv/data/medallion/silver/trades/ETHUSDT \
  --candles-dir /srv/data/medallion/silver/candles/ETHUSDT \
  --ledger-path /tmp/neg-ledger.jsonl \
  --require-marker /srv/data/.lenovosrv-data-volume-MISSING
echo "exit_code=$?"
```

**Resultado esperado:** 8a `User=1000:1000 Revision=79b1de5b8fc827397e608b698d315498b36ca92d`.
8b imprime `ERROR: marker ausente: /srv/data/.lenovosrv-data-volume-MISSING` y `exit_code=1`
(FAIL CLOSED; no se escribe ledger).

### Paso 9 (S) — Paper / certificación y splits intactos

```bash
CID=$(docker ps -q --filter name=self-evaluating-trading-agent-paper-runner-1)
docker inspect -f '{{.State.Status}} since {{.State.StartedAt}}' "$CID"
ls /srv/data/medallion/gold/replay-datasets/ETHUSDT/ | grep -icE 'holdout|walk|final'
cat /srv/data/.lenovosrv-data-volume
```

**Resultado esperado:** `running since 2026-09-19T04:00:04.763010163Z` (sin cambios);
`0` datasets holdout/walk (ninguno leído); marker `LENOVO_DATA`. En local:
`cat holdout/v1.state.json` → `"state": "PRISTINE"`.

## Evidencia a adjuntar

> Capturas, salidas de comando o logs que respalden cada resultado.

- Salida de cada paso (copiar/pegar las líneas de resultado relevantes).
- `sha256sum` del ledger del paso 6.
- Salida de `git rev-parse HEAD` (precondición 1).

## Resultado observado

| Paso | Resultado observado | ¿Coincide? (SÍ/NO) | Notas |
|---|---|---|---|
| 1 | PASS (usuario) | SÍ | Bronze: `downloaded=0 skipped=3 total=3` |
| 2 | PASS (usuario) | SÍ | Silver: `transformed=3`; 3/3 MATCH vs canónico |
| 3 | PASS (usuario) | SÍ | Candles: `transformed=21`; 3/3 MATCH; 15m `42c78757…` |
| 4 | PASS (usuario) | SÍ | Gold: `dataset_id=gold-replay-a8c49e0b…`, manifest `9411a4e0…` |
| 5 | PASS (usuario) | SÍ | Replay `6d64b62b…`; segunda corrida `skipped`; tests no-lookahead PASS (ver incidencia I-1) |
| 6 | PASS (usuario) | SÍ | Paridad signal/candle hash OLD==NEW; netos coincidentes (ver incidencia I-2) |
| 7 | PASS (usuario) | SÍ | Aislamiento compose + imagen (`User=1000:1000`, revisión SHA) |
| 8 | PASS (usuario) | SÍ | Marker negativo `exit_code=1` (FAIL CLOSED) |
| 9 | PASS (usuario) | SÍ | paper-runner `running since 2026-09-19T04:00:04.763010163Z`; `0` datasets holdout/walk; `PRISTINE` |

## Incidencias encontradas

> Desviaciones, errores o comportamientos inesperados.

- **I-1 (harness, resuelto):** el Paso 5 inicial escribía en `/srv/fast/medallion/uat/`, que quedó
  `root-owned` por los pasos previos ejecutados con `--user 0:0`; el `mkdir` del host (uid 1000)
  falló (`Permission denied`). Corregido escribiendo en `/srv/fast/medallion/replay-work/uat-replay/`
  (propiedad de `administrador`). **No es defecto del motor de replay.** Reintentado → PASS.
- **I-2 (harness, resuelto):** el Paso 6 inicial leía `summary["net_pnl"]`, pero el campo está
  anidado en `summary["metrics"]["net_pnl"]`. Corregido. **No es defecto de datos.** Reintentado → PASS.

---

## VEREDICTO UAT: APPROVED
<!-- Sustituir PENDING por APPROVED o REJECTED. gate_check exige el veredicto APPROVED visible (los comentarios HTML no cuentan) al check uat-approved -->
Decisor: usuario  Fecha: 2026-09-29
Comentario: UAT Fase 23 aprobado por el usuario. 9/9 pasos PASS. Las incidencias I-1 e I-2 fueron del harness, quedaron documentadas, corregidas y revalidadas; no hubo fallos de producto.
