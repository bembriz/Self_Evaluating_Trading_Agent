# Arquitectura Medallion — Market Data + Trade-Level Replay + Plataforma lenovosrv

**Versión:** 1.0 (M0)
**Fecha:** 2026-09-24
**Estado:** proposed — pendiente de aprobación en gate M0
**Rama:** `medalion` (base `962c971249fd34671d0ace323100aac984fd44ff`)
**ADRs asociados:** ADR-0005 (dos relojes), ADR-0006 (plataforma compartida), ADR-0007 (tiering de almacenamiento)

---

## 1. Problema

El replay actual de SETA decide y ejecuta a escala de vela (`src/application/services/backtest_engine.py`, `src/interfaces/cli/replay.py`): la señal se genera en el cierre de la vela `i` y se ejecuta en el open de la vela `i+1`. Ese modelo de **un solo reloj (velas)** no es representativo de la ejecución real porque:

1. **No existe cronología intra-vela**: dentro de una vela de 15m ocurren miles de trades reales con secuencia propia; SL/TP/trailing "saltan" a resolución de vela y el orden real de triggers se pierde.
2. **No hay contrato de auditoría trade-a-trade**: `trigger_timestamp` vs `fill_timestamp`, MFE/MAE intra-trade, `exit_reason` explícito y hashes de dataset por trade no están garantizados en el camino de replay.
3. **Los resultados históricos vigentes** (fases 21R/22: Baseline/Donchian/Bollinger, todos FAIL en viabilidad absoluta) son evidencia del **modelo de ejecución antiguo**, no la base definitiva de selección de estrategias (§21).
4. **La ingesta actual es solo velas** (`MarketDataClient.fetch_candles` → CSV+manifest vía `LocalDatasetStore`): no hayBronze de trades individuales, ni Silver canónico, ni capa Gold como manifiesto de replay.
5. **lenovosrv no está dimensionado como plataforma compartida**: servicios de infraestructura duplicados por aplicación (Caddy propio de GastosIA, Postgres del proyecto SETA usado además por GastosIA), disco SATA en NTFS sin consumidor designado, y regla de gobernanza que impide de forma absoluta reutilizar ese disco.

## 2. Limitaciones del replay actual (estado verificado en repo)

| # | Limitación | Evidencia (file:line) |
|---|---|---|
| L1 | Un solo reloj (velas); ejecución al open de la vela siguiente | `src/application/services/backtest_engine.py:52-66` |
| L2 | Sin eventos de trade; SL/TP/trailing no evalúan cronología intra-vela | `backtest_engine.run` solo llama `strategy.on_candle` |
| L3 | `trigger` y `fill` son indistinguibles (un único precio/timestamp) | `backtest_engine._execute` (`backtest_engine.py:89-97`) |
| L4 | Replay CLI emite decisiones por vela, sin traza de trade auditada | `src/interfaces/cli/replay.py:86-107` |
| L5 | Ingesta limitada a klines REST (`/v5/market/kline`) | `src/application/services/historical_data.py:11`, `src/application/ports/market_data.py:10-17` |
| L6 | Persistencia solo CSV de velas + manifest | `src/infrastructure/storage/dataset_store.py:14-60` |
| L7 | MFE/MAE existen solo en evaluación post-trade, no como serie de replay | `src/domain/evaluation/outcome.py:27-58` |
| L8 | El dataset congelado `BYBIT_ETHBTC_V001` es velas 15m/1h/4h; sin trades individuales | `docs/datasets/BYBIT_ETHBTC_V001.manifest.json`, `splits/v1.json` |

**Lo que SÍ está y se preserva:** determinismo (ARepr-0003), no-lookahead (`data-leakage`), guards de split (`src/lab/frozen_dataset.py:42-59`: holdout denegado por defecto, WALK_FORWARD con token), fees/slippage modelados, contabilidad de portfolio, Risk Engine determinista (inviolable).

## 3. Arquitectura Medallion objetivo

```text
Bybit public trade archives (diarios .csv.gz)
        │  (download atómico + sha256 + idempotencia)
        ▼
┌───────────────┐   byte-for-byte, inmutable
│    BRONZE     │   /srv/data/medallion/bronze/bybit/<market>/<symbol>/
└───────┬───────┘
        │  normalización determinista (stdlib)
        ▼
┌───────────────┐   esquema canónico + orden total
│ SILVER TRADES │   /srv/data/medallion/silver/trades/
└───────┬───────┘
        │  agregación determinista OHLCV
        ├──────────────────────────────┐
        ▼                              ▼
┌───────────────┐              ┌───────────────┐
│ SILVER CANDLES│              │   (validación │
│ 1m..1d        │              │  vs Kline API │
└───────┬───────┘              │  solo check)  │
        │                      └───────────────┘
        ▼
┌───────────────┐   manifiesto inmutable mínimo (hashes)
│     GOLD      │   /srv/data/medallion/gold/
│ replay dataset│
└───────┬───────┘
        │  replay de dos relojes (estrategia=velas confirmadas,
        ▼  ejecución=secuencia cronológica de trades)
  Trade-Level Replay Engine (M7) → auditoría trade-a-trade
```

Regla transversal: **el HDD (`/srv/data`) es canónico; NVMe (`/srv/fast`) es caché desechable y reproducible** (§6, ADR-0007).

## 4. Bronze — archivos oficiales de trades

- **Fuente:** archivos históricos públicos de trades de Bybit (diarios `.csv.gz`); candles NO se descargan como fuente canónica.
- **Inmutabilidad byte-a-byte:** cada archivo se conserva exactamente como llega; ninguna transformación en esta capa.
- **Metadatos por archivo:** `source_url`, `symbol`, `market` (spot/linear), `date`, `size`, `sha256`, `download_timestamp`, `schema_version`.
- **Patrón atómico:** `download → <file>.csv.gz.part` → verificar `sha256` → `rename(2)` atómico → registro en manifiesto Bronze.
- **Solo archivos diarios inicialmente** (no mensuales/agregados) para particionado simple y reproducible.
- **Particionado:** `bronze/bybit/<market>/<symbol>/date=YYYY-MM-DD/*.csv.gz` (patrón Hive, determinista).
- **Idempotencia:** ver §12.

## 5. Silver — trades canónicos

Esquema canónico (todas las columnas obligatorias salvo indicado):

| Campo | Notas |
|---|---|
| `event_timestamp` | ms UTC del trade (reloj del intercambio) |
| `symbol` | p.ej. ETHUSDT |
| `price` | float (mismo criterio IEEE-754 que ADR-0002/0003) |
| `quantity` | float |
| `taker_side` | `buy` \| `sell` |
| `native_trade_id` | nullable |
| `native_sequence` | nullable |
| `source_file` | ruta relativa Bronze |
| `source_file_sha256` | linaje exacto |
| `source_row_number` | índice físico de fila en el archivo origen |

**Orden total:** `(event_timestamp, native_sequence)` cuando exista secuencia nativa; si no, `(event_timestamp, source_file, source_row_number)`. Si la ordenación exacta del exchange no puede probarse para un rango, el dataset declara `ORDERING_FIDELITY=PARTIAL` en el manifiesto Gold (nunca se silencia).

**Prohibido deduplicar por `(timestamp, price, quantity)`:** trades legítimos pueden compartir los tres; la unicidad se expresa con `native_trade_id` cuando existe, y en caso contrario con la combinación `(source_file, source_row_number)`.

**Determinismo:** misma entrada + misma versión ⇒ salida byte-idéntica (hash de salida registrado).

## 6. Silver — candles derivadas

- Derivadas **únicamente** de Silver trades (nunca de una fuente independiente).
- Timeframes iniciales: `1m 5m 15m 30m 1h 4h 1d`.
- Clave natural: `(symbol, timeframe, candle_open_timestamp)`.
- Agregación determinista: OHLCV por ventana calendario UTC alineada al timestamp; sin velas parciales en el dataset canónico (la vela se emite solo al cerrarse).
- **La API Kline de Bybit SOLO se usa para validación/reconciliación** (comparar muestra OHLCV derivada vs oficial; discrepancia ⇒ FAIL y bloqueo, jamás sobrescribe lo derivado).
- Dataset de candles descargado independientemente **nunca** es canónico.

## 7. Gold — manifiesto de replay inmutable

Gold **no duplica** datos de mercado: es un manifiesto mínimo e inmutable que referencia hashes.

Campos obligatorios: `dataset_id`, `source_hashes` (Bronze), `silver_hashes` (trades + candles), `symbols`, `range`, `allowed_split` (solo `DEVELOPMENT` en M0–M6), `timeframes`, `ordering_fidelity`, `execution_model_version`, `fee_model_version`, `slippage_model_version`, `created_by_version`.

- Escritura una sola vez; cualquier cambio ⇒ nuevo `dataset_id` + nuevo experimento (regla crítica §4.9 aplicada a datasets).
- Ubicación: `/srv/data/medallion/gold/` (caché en NVMe permitida, nunca canónica).

## 8. Replay de dos relojes (ADR-0005)

```text
RELOJ DE ESTRATEGIA  → velas CONFIRMADAS (15m principal; contexto 1h/4h)
RELOJ DE EJECUCIÓN   → cada trade público ETHUSDT en orden cronológico estricto
```

Reglas:

1. La estrategia solo ve velas confirmadas: **cero velas incompletas** (sin leakage).
2. La decisión ocurre **después** de la confirmación de la vela.
3. `BUY`/`SELL` **nunca** se ejecutan retrospectivamente en el close de una vela anterior: la decisión en t se materializa en el **primer trade elegible siguiente** según la política de ejecución.
4. Con posición abierta, **cada evento de ejecución** evalúa: Stop Loss, Take Profit, Trailing Stop, MFE, MAE, precio máximo — **gana el primer trigger cronológico real**.
5. Determinismo: misma entrada + misma versión ⇒ hash de traza idéntico.

## 9. Fidelidad de ejecución

Etiqueta inicial del modelo de ejecución: **`TRADE_SEQUENCE_TAKER_PROXY`**.

| Afirmación SÍ | Afirmación NO |
|---|---|
| Cronología histórica de trades | Posición en cola real |
| Slippage existente (modelo conservador) | Spread real del book |
| Fee taker existente (Bybit spot) | Profundidad real del order book |
| | Market impact |
| | Fill exacto propio |

Nivel de fidelidad futuro posible: replay de order-book histórico — fuera de alcance de M0–M10 y sujeto a nueva propuesta.

## 10. Trigger vs fill

Conceptos separados y **nunca** silenciosamente identificados:

- `*_trigger_timestamp`: instante en que la condición (señal/SL/TP/trailing) se dispara en la cronología de ejecución.
- `*_fill_timestamp`: instante en que se materializa el fill según `TRADE_SEQUENCE_TAKER_PROXY` (normalmente el siguiente trade elegible ≥ trigger).
- `*_reference_price`: precio de referencia de la condición (p.ej. close de vela de decisión o nivel de stop).
- `*_execution_price`: precio real aplicado por el fill (trade histórico + slippage).

## 11. Contrato de auditoría trade-a-trade

Cada trade completado del replay debe exponer (campos obligatorios):

```text
entry_signal_timestamp, entry_trigger_timestamp, entry_fill_timestamp
entry_reference_price, entry_execution_price
atr_at_entry, initial_stop, initial_target
MFE, MAE, highest_price
exit_trigger_timestamp, exit_fill_timestamp
exit_reason
exit_reference_price, exit_execution_price
quantity, fees, slippage, gross_pnl, net_pnl, holding_ms
strategy_version, risk_version, execution_model_version
dataset_id, dataset_sha
```

- Los trades completados **normales no pueden tener `exit_reason=UNKNOWN`** (catálogo cerrado: `stop_loss`, `take_profit`, `trailing_stop`, `strategy_exit`, `max_time_in_position`, `end_of_dataset`… alineado con la clasificación ya usada en phase-22-b).
- Reutilizar donde exista: `exit_reason` en `paper_engine` (`src/application/services/paper_engine.py:48,240`) y `mfe/mae` en `src/domain/evaluation/outcome.py`.

## 12. Idempotencia

| Capa | Regla |
|---|---|
| Bronze download | `archivo existe + sha256 coincide` → **SKIP**; `existe + sha256 distinto` → **FAIL CLOSED** (no sobrescribe); interrupción → `.part` se descarta/regenera |
| Silver transform | entrada (hash Bronze) + versión de transformador ⇒ hash de salida fijo; re-ejecutar no duplica ni muta |
| Candles | idem, además clave natural única `(symbol, timeframe, open_ts)` |
| Gold | escritura única; intento de reescritura con contenido distinto ⇒ FAIL |
| Replay | misma versión + mismo dataset ⇒ mismo hash de traza |

## 13. Protección de splits

- Los guards actuales de `FrozenDatasetAdapter` (`src/lab/frozen_dataset.py:42-59`) son la referencia: **FINAL_HOLDOUT denegado por defecto** en cualquier rango, WALK_FORWARD solo con token autorizado.
- M0–M6: **solo `DEVELOPMENT`** (`splits/v1.json`: 62 208 filas 15m, 2023-09-08 → 2025-06-17).
- `WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0` — verificable por tests (corruptor temporal + contadores de acceso).
- **No descargar ni procesar particiones restringidas aunque Bybit las publique libremente:** el filtro de split aplica también a Bronze (el downloader rechaza rangos fuera de `allowed_split` antes de la red).
- Holdout congelado: `HOLDOUT_STATE=PRISTINE` se mantiene hasta el gate correspondiente.

## 14. Tiering de almacenamiento (ADR-0007)

| Tier | Contenido | Dispositivo |
|---|---|---|
| **HOT** | datasets PostgreSQL activos, estado de app, working set de replay, streams ordenados temporales, índices activos, caché de experimentos | NVMe (`/`, `/srv/docker`, `/srv/fast`) |
| **WARM** | particiones de desarrollo reutilizadas, caché opcional de trades, salidas de replay activas | NVMe cuando hay capacidad |
| **COLD** | Bronze inmutable, Silver histórico canónico, Gold antiguo, evidencia de replay antigua, recibos/imágenes, backups | SATA HDD (`/srv/data`, futuro) |

**Principio duro:** el HDD es el **almacén persistente autoritativo** de los datos masivos de Medallion. La caché NVMe es **desechable y reproducible**: borrar `/srv/fast/medallion` **nunca** puede destruir el dataset canónico.

## 15. Aceleración SSD/NVMe + protección de capacidad

Layout propuesto (NO creado en M0):

```text
/srv/fast/medallion/
├── cache/        # réplicas de particiones HDD → NVMe (desechable)
├── replay-work/  # working set activo de replay (desechable)
├── tmp/          # transformaciones temporales (desechable)
└── indexes/      # índices derivados reproducibles (desechable)
```

**Medición actual de la raíz NVMe (lenovosrv, 2026-09-24):** total 455 GB · usado 19 GB · libre 417 GB (5%).

Reglas de diseño (derivadas de la medición, no hard-codeadas a ciegas):

```text
SSD_MIN_FREE_GB   = max(50 GB, 10% × total)   → hoy max(50, 45.5) = 50 GB
SSD_CACHE_MAX_GB  = min(config, 20% × total, libre − SSD_MIN_FREE_GB)
                    → techo medido hoy: min(config, 91, 367); config inicial propuesta = 64 GB
```

Safeguards (fail-closed, obligatorios en todo pipeline M3+):

1. Preflight: si `libre < SSD_MIN_FREE_GB` ⇒ **ABORT** (no degrada Docker/PostgreSQL).
2. Caché con cuota `SSD_CACHE_MAX_GB`; superada ⇒ rechaza la petición de staging (no acepta más).
3. Limpieza **solo** de árboles marcados como reproducibles (`/srv/fast/**`); jamás datos canónicos, Docker ni volúmenes PostgreSQL.
4. Recalcular ambos umbrales en cada gate M* con `df` medido; registrar en evidencia.
5. El pipeline jamás auto-borra nada fuera de `/srv/fast`.

## 16. Almacenamiento canónico HDD

Layout objetivo (NO creado en M0; requiere gate destructivo M1):

```text
/srv/data/
├── medallion/
│   ├── bronze/bybit/<market>/<symbol>/date=YYYY-MM-DD/
│   ├── silver/trades/…   silver/candles/<tf>/…
│   ├── gold/
│   ├── state/
│   └── logs/
├── gastosia/{receipts,attachments,data}/
└── backups/{postgres,gastosia,seta}/
```

Plan de formato futuro (documentado, **NO ejecutado en M0** — ver §24/§25): device `/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR` (ST1000LM035-1RK1, serial WDEV3QGR, 931,5G, hoy NTFS `Warehouse` montado en `/mnt/warehouse`) → GPT + 1 partición + ext4 + label **`LENOVO_DATA`** + fstab **solo por UUID** + mount `/srv/data`. Marker fail-closed `/srv/data/.lenovosrv-data-volume` (`{"uuid":…,"label":"LENOVO_DATA",…}`); todo pipeline debe abortar salvo `mountpoint -q /srv/data` **Y** marker UUID == UUID real del filesystem montado.

## 17. Plataforma compartida lenovosrv (ADR-0006)

**Principio: `SHARE INFRASTRUCTURE · ISOLATE BUSINESS LOGIC`.**

```text
/srv/docker/
├── platform/
│   ├── compose.yaml
│   ├── postgres/     # platform-postgres (1 motor, 1 BD + 1 rol por solución)
│   ├── caddy/        # platform-caddy (único publicador 80/443)
│   ├── monitoring/   # platform-prometheus + platform-grafana
│   └── backup/       # platform-backup (futuro, solo si hace falta)
├── seta/compose.yaml
├── gastosia/compose.yaml
└── future-app/compose.yaml
```

- Servicios compartidos objetivo: `platform-postgres`, `platform-caddy`, `platform-prometheus`, `platform-grafana`; opcionales futuros `platform-redis`, `platform-backup` **solo cuando exista necesidad real** (no crear contenedores innecesarios).
- **FastAPI NO es infraestructura compartida:** cada solución conserva su contenedor de aplicación (`gastosia-app`, `seta-api`, …). Dependencias, ciclos de despliegue, fallos, versiones y fronteras de seguridad independientes. Prohibido el monolito FastAPI común.
- `M0 NO` despliega nada: solo documenta.

## 18. PostgreSQL compartido

```text
platform-postgres
├── trading_agent   → rol seta_app
├── gastos_ia       → rol gastosia_app
└── future_db       → rol future_app_role
```

Reglas:

- **Un motor/contenedor, una BD por solución, un rol por solución.**
- Least privilege; sin permisos cross-database de aplicación; sin credenciales compartidas entre aplicaciones.
- Cada solución posee sus migraciones; backup y restore **por base de datos**; el ciclo de vida del motor lo posee la plataforma.
- **M0 NO migra ninguna base** y NO toca el PostgreSQL actual en certificación (el motor actual aloja además `gastos_ia` — acoplamiento documentado en §21, se resuelve en la etapa de migración de plataforma, tras/durante coordinación con la certificación).

## 19. Reverse proxy compartido

- Único publicador de **80/443**: `platform-caddy`.
- Aplicaciones **internas** en `platform-net`: `gastosia-app:8000`, `seta-api:8000`, `platform-grafana:3000`, etc.
- M0 **NO** migra el Caddy actual de GastosIA (proyecto `gastos-ia`, compose en `/srv/docker/gastos-ia/compose.yaml`): solo plan.

## 20. Red Docker

```text
platform-net          (externa, compartida: acceso a postgres/caddy/monitoring)
seta-private          (aislamiento interno SETA)
gastosia-private
medallion-private
```

- Cada solución usa su red privada por defecto; se conecta a `platform-net` **solo** si necesita infraestructura compartida.
- **PostgreSQL jamás expuesto públicamente** (solo `platform-net`; host binding loopback como máximo para operación).
- Evitar la práctica actual de que la app GastosIA viva además en la red del proyecto SETA (acoplamiento observable en `docker inspect gastos-ia-app`).

## 21. Coexistencia GastosIA

Estado verificado (descubrimiento 2026-09-24, read-only):

| Activo | Ubicación | Disco |
|---|---|---|
| Compose/config/cred | `/srv/docker/gastos-ia/` | NVMe |
| Datos persistentes (recibos) | `/mnt/warehouse/GastosIA/` (~0,6 MB, 20 archivos) | SATA |
| Volúmenes docker (caddy) | `/srv/docker/volumes/gastos-ia_*` | NVMe |
| BD `gastos_ia` (8,3 MB) | **dentro del contenedor PostgreSQL de SETA** | NVMe |
| Legados | `Hyper-V/VirtualMachines/GastosIA.vhdx` (21 GB), `/mnt/warehouse/PostgreSQL` (228 MB) | SATA |

Plan de migración (documentado; **NO ejecutar durante M0 ni con certificación activa sin gate**):

1. **M1/M2:** tras formato HDD, `gastosia/receipts|attachments|data` → `/srv/data/gastosia`; application code permanece en `/srv/docker/gastosia`.
2. **Plataforma (post-M2):** `gastos_ia` migra al `platform-postgres` con `pg_dump`/`pg_restore` lógicos, rol `gastosia_app`; el motor de SETA queda solo con `trading_agent`.
3. **Caddy:** GastosIA pasa a ser backend interno de `platform-caddy`.
4. **Red:** app en `gastosia-private` + `platform-net`; eliminar dependencia de la red SETA.
5. Backup por BD independiente desde `platform-backup` (§22).
6. Cada paso exige su propio gate y su test de restore; la certificación paper vigente NO se interrumpe en M0–M10 sin aprobación explícita.

## 22. Arquitectura de backup (diseño; NO implementar en M0)

```text
/srv/data/backups/
├── postgres/<db>/pg_dump-<db>-<ts>.dump + .sha256 + manifest.json
├── gastosia/    (data + config; ver gate M0-II)
└── seta/        (evidencia/estado)
```

- Dumps **lógicos** por base de datos (`pg_dump -Fc`), independientes por solución.
- Ciclo: `backup → hash → manifest → retención → test de restore periódico`.
- Restore probado en **contenedor aislado de prueba** (nunca encima del motor productivo).
- Automatización: futura, gated (Dependency Proposal si requiere nuevos componentes).

## 23. Arquitectura de despliegue

- **Hoy:** compose por proyecto en `/srv/docker/<proyecto>/compose.yaml` (SETA y GastosIA independientes; Docker root en NVMe `/srv/docker`).
- **Objetivo:** `platform/` + `<solución>/` como en §17, red externa `platform-net`, datos canónicos en `/srv/data` (HDD) y caché en `/srv/fast` (NVMe).
- Las workers de Medallion (M8) se despliegan como servicios del proyecto `medallion` (o `seta` si se decide integración), leyendo canónico de HDD vía staging a NVMe.
- Migración de rutas de los sistemas en marcha: **NO en M0**; ver etapas §24.

## 24. Etapas de migración (gates internos; no saltar)

```text
M0    Arquitectura + gobernanza + skills + diseño storage/plataforma   ← ESTE GATE
M0-I  Revalidación de infraestructura (read-only)
M0-II Backup de GastosIA + test de restore aislado
M1    Reformateo destructivo HDD + mount /srv/data           (USER GATE explícito)
M2    Fundación de directorios/red de plataforma
M3    Ingesta Bronze (trades)
M4    Silver trades canónicos
M5    Silver candles multi-timeframe
M6    Gold replay dataset
M7    Motor de Trade-Level Replay
M8    Despliegue de workers Medallion en lenovosrv
M9    Re-ejecución de estrategias existentes (Baseline/Donchian/Bollinger)
M10   UAT + auditoría + candidato a integración
```

**Representación en el arnés (fase 23 / iniciativa Medallion):** el mecanismo mínimo y seguro ya existe y se usó para la fase `16b`:

```bash
python3 harness/scripts/progress.py add-phase \
  --phase 23 \
  --titulo "Medallion Market Data + Trade-Level Replay" \
  --deliverable id=descripcion          # repetible por entregable
python3 harness/scripts/new_phase.py --phase 23   # scaffoldea docs/phases/23/evidence + UAT + reporte
```

- El ledger **solo** se muta vía scripts (`meta.mutacion_solo_scripts: true`); **prohibido editar `harness/state/progress.yaml` a mano**.
- `gate_check.py --phase 23` funciona una vez registrada la fase (lee `docs/phases/23/evidence/`).
- Los trabajo post-18 (17A–22) se documentaron en `docs/phases/<X>/` **sin** entrada en el ledger; la vía preferente para Medallion es `add-phase` (contabilidad completa: %, gates, ETA). **M0 NO ejecuta `add-phase`** (solo documenta la estrategia); se ejecutará al iniciar la fase 23.
- Si se necesitan sub-fases tipo `23A/23B`, el ledger ya admite claves no numéricas (`add-phase --phase 23A`).

## 25. Restricciones de seguridad

1. **Certificación paper intocable:** no modificar `/srv/docker/self-evaluating-trading-agent`, no reiniciar `paper-runner`, no recrear/rebuild, no tocar `WALK_FORWARD`/`FINAL_HOLDOUT`, no tocar safeguard/certification.
2. **M0 sin dependencias nuevas:** cero `pandas/polars/pyarrow/duckdb/redis`/imágenes; diseño + stdlib. Futuras: Dependency Proposal gated (§31 del gate).
3. **M0 destructivo = nada:** sin formato, partición, fstab, montajes, deploy, commit, push (§24–25 del gate; `HDD_FORMAT_EXECUTED=NO`).
4. **Identidad física por by-id**, nunca `/dev/sda` a secas.
5. **Preformato GastosIA (gate M0-II/M1):** `GASTOSIA_BACKUP_COMPLETE=YES`, `GASTOSIA_BACKUP_HASH_VERIFIED=YES`, `GASTOSIA_DATABASE_BACKUP=PASS`, `GASTOSIA_RESTORE_TEST=PASS`, `DISK_IDENTITY_MATCH=YES` + **USER APPROVAL explícito**.
6. **Splits:** `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`, `HOLDOUT_STATE=PRISTINE`.
7. **Risk Engine y LLM:** invariants de `risk-engine` intactos; el replay NO altera autoridad de riesgo.
8. **Conflicto de gobernanza (§26 del gate) — localizado y documentado:**
   - **Regla exacta:** `~/.config/opencode/AGENTS.md:49` → *"`/mnt/warehouse` = disco NTFS de 1 TB montado automático vía fstab (ntfs3), contiene datos personales — NO formatear ni borrar jamás"*.
   - **Conflicto:** decisión explícita del usuario en M0 → *"Solo GastosIA debe preservarse"*; el disco secundario ES el warehouse.
   - **Redacción corregida mínima propuesta (NO aplicada en M0; requiere aprobación):**

```text
- Almacenamiento: raíz / = 455 GB (LVM sobre NVMe Samsung 970 EVO).
  Volumen de datos del servidor (hoy /mnt/warehouse NTFS 1 TB; futuro /srv/data ext4 LENOVO_DATA):
  GastosIA (datos, imágenes, BD) DEBE preservarse mediante backup + test de restore
  ANTES de cualquier destrucción. Toda acción destructiva del disco exige USER GATE
  explícito e identidad física verificada por /dev/disk/by-id/.
  El contenido no protegido del warehouse puede destruirse únicamente tras gate aprobado.
```

   - **No se debilitan** las salvaguardas generales: siguen vigentes USER GATE, verificación by-id, backup previo y prohibición de acciones destructivas sin aprobación.

## 26. Tests de aceptación (plan de diseño — se implementan en M3+)

**Bronze:** idempotencia de descarga (SKIP si hash coincide) · conflicto de hash ⇒ FAIL CLOSED · recuperación de `.part` interrumpido · metadatos completos.
**Silver trades:** normalización determinista · orden total estable · preservación de duplicados legítimos · hash de salida idéntico entre corridas.
**Candles:** agregación determinista · bordes de vela correctos (close=next open, sin solapes) · reconciliación vs muestra Kline.
**Replay:** sin lookahead · SL antes que TP · TP antes que SL · cronología de trailing · sin fill retrospectivo en la misma vela · separación trigger/fill · replay idéntico ⇒ hash de traza idéntico.
**Auditoría:** `exit_reason` explícito nunca `UNKNOWN` · MFE/MAE presentes · timestamps exactos (signal/trigger/fill).
**Storage:** preflight de montaje HDD · validación de marker UUID · guard de espacio libre SSD (`SSD_MIN_FREE_GB`) · caché desechable (borrar `/srv/fast/medallion` no afecta canónico) · cuota `SSD_CACHE_MAX_GB`.
**Plataforma:** aislamiento de BD · aislamiento de rol · PostgreSQL no expuesto públicamente.
**Data policy:** solo `DEVELOPMENT` · `WALK_FORWARD_READS=0` · `FINAL_HOLDOUT_READS=0`.

---

## Apéndice A — Blast radius (índice codebase-memory, generación 2026-09-19)

| Componente | Archivos llamadores | Impacto M0 |
|---|---|---|
| `paper_engine.py` | 30 | 0 (M0 no toca src/) |
| `frozen_dataset.py` | 28 (harness phase18–20 + lab) | 0; M7 extiende guards sin cambiar semántica |
| `dataset_store.py` | 9 (CLI backtest/download/replay) | 0; M4–M6 añaden almacén de trades |
| `backtest_engine.py` | 5 | 0; M7 añade motor de dos relojes (paralelo, no reemplazo inmediato) |
| `historical_data.py` | 3 | 0; M3 añade pipeline de trades |
| `replay.py` | 3 | 0; M7 extiende CLI |

M0 modifica **solo documentos/skills** ⇒ blast radius de runtime = 0.

## Apéndice B — Hechos de lenovosrv revalidados (2026-09-24, read-only)

- Host: `lenovosrv`, Ubuntu 24.04.4 LTS, kernel 6.8.0-138-generic.
- NVMe `Samsung SSD 970 EVO 500GB` (S466NX0KC36133J): LVM `ubuntu--vg-ubuntu--lv` ext4 = `/` (455G, 19G usados, 417G libres); Docker root `/srv/docker` (en NVMe).
- SATA `ST1000LM035-1RK1` serial `WDEV3QGR` vía `/dev/disk/by-id/ata-ST1000LM035-1RK172_WDEV3QGR` → `sda`; `sda1` NTFS label `Warehouse` UUID `0ADC29B7DC299DC7` → `/mnt/warehouse` (932G, 489G usados); fstab `UUID=… nofail`.
- Contenedores SETA (paper-runner/grafana/prometheus/postgres) **Up, sin montajes sobre `/mnt/warehouse`**; certificación intacta.
