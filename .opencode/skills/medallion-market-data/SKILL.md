---
name: medallion-market-data
description: Usar al implementar o modificar el pipeline Medallion de market data (Bronze/Silver/Gold de trades de Bybit, candles derivadas, manifiesto de replay inmutable, idempotencia de descargas, tiering de almacenamiento NVMe/HDD, staging a /srv/fast, guards de splits en ingestas), o al diseñar workers de ingesta/transformación en lenovosrv
---

# medallion-market-data — Pipeline Medallion (Bronze → Silver → Gold)

## Propósito

Ingesta y transformación determinista de **trades individuales** de Bybit en capas Bronze/Silver/Gold, con linaje completo, idempotencia, inmutabilidad y particionado por split — base del Trade-Level Replay (dos relojes). Diseño de referencia: `docs/design/medallion-replay-architecture.md` + ADR-0005/0006/0007.

## Cuándo usar

- Implementar descarga de archivos históricos públicos de trades (Bronze).
- Normalizar trades canónicos (Silver trades) y derivar candles (Silver candles).
- Construir el manifiesto Gold de replay.
- Cualquier cambio a almacenamiento/staging de Medallion en lenovosrv (`/srv/data`, `/srv/fast`).
- Workers M8 de ingesta/transformación.

**Cuándo NO:** replay/ejecución de estrategias (backtesting); adapters REST/WS/Testnet en vivo (bybit-integration); lógica de riesgo (risk-engine); paper trading (paper-engine).

## Invariantes duras

1. **Bronze inmutable:** byte-a-byte como llega; `.part` → sha256 → `rename(2)` atómico; hash existente ≠ hash recibido ⇒ **FAIL CLOSED**, jamás sobrescribir.
2. **Idempotencia:** re-descarga con hash coincidente ⇒ SKIP; re-transformar ⇒ mismo hash de salida; Gold re-escrito con contenido distinto ⇒ FAIL.
3. **Determinismo:** misma entrada + misma versión de transformador ⇒ salida byte-idéntica; versiones registradas en linaje.
4. **Sin deduplicar trades por `(timestamp, price, quantity)`:** unicidad solo con `native_trade_id` o `(source_file, source_row_number)`.
5. **Orden total declarado:** `(event_timestamp, native_sequence)` o fallback documentado; orden no demostrable ⇒ `ORDERING_FIDELITY=PARTIAL` en Gold, nunca silenciar.
6. **Candles SOLO derivadas de Silver trades;** API Kline únicamente para reconciliación (discrepancia ⇒ FAIL, no sobrescribe).
7. **Splits antes de la red:** downloader rechaza rangos fuera de `allowed_split` (M0–M6 = solo `DEVELOPMENT`) ANTES de descargar; `WALK_FORWARD_READS=0`, `FINAL_HOLDOUT_READS=0`.
8. **Tiering (ADR-0007):** HDD `/srv/data` = canónico autoritativo; NVMe `/srv/fast/**` = caché desechable y reproducible. Borrar `/srv/fast` jamás destruye datos.
9. **Safeguards de capacidad:** preflight con `SSD_MIN_FREE_GB` (fail-closed, hoy 50 GB), cuota `SSD_CACHE_MAX_GB` (config inicial 64 GB), limpieza solo de árboles reproducibles; recalcular por medición en cada gate M*.
10. **Identidad de disco por `/dev/disk/by-id/…`,** nunca `/dev/sda` a secas; marker `/srv/data/.lenovosrv-data-volume` verificado antes de usar el volumen.

## Capas

```text
Bronze:  /srv/data/medallion/bronze/bybit/<market>/<symbol>/date=YYYY-MM-DD/*.csv.gz  (+ metadatos sha256/url/schema)
Silver:  silver/trades/ (esquema canónico: event_timestamp, symbol, price, quantity, taker_side, native_trade_id?, native_sequence?, source_file, source_file_sha256, source_row_number)
         silver/candles/<tf>/ (1m 5m 15m 30m 1h 4h 1d; clave (symbol, tf, open_ts); solo velas cerradas)
Gold:    gold/ (manifiesto mínimo inmutable: dataset_id, source/silver hashes, range, allowed_split, timeframes, ordering_fidelity, execution_model_version, fee/slippage versions)
```

## Errores comunes

- Staging o escritura directa en la raíz NVMe sin preflight de espacio (llena `/`, tumba Docker/PG).
- Tratar Kline API como fuente canónica en vez de validación.
- Descargar rango holdout "solo para mirar" (viola split policy aunque Bybit lo publique).
- Sobre-escribir Bronze para "corregir" un hash — se descarta y se re-baja a nombre nuevo con incidente.
- Tratar la caché NVMe como canónica (guardar allí lo único).

## Referencias

- `docs/design/medallion-replay-architecture.md` §4–§16; ADR-0005/0006/0007.
- Skills: data-pipeline-quality, bybit-integration (descubrimiento de archivos), data-leakage (splits), infra-control (sin installs sin proposal), error-handling-resilience.
