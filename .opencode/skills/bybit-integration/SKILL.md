---
name: bybit-integration
description: Usar al implementar adapters de Bybit (REST histórico, WebSocket producción, órdenes Testnet), manejar autenticación/rate limits/reconexiones, grabar fixtures de mensajes reales, o al consumir los archivos históricos públicos de trades de Bybit (descubrimiento de archivos, descarga idempotente, preservación raw, detección/versión de esquema)
---

# bybit-integration — Integración con Bybit (REST/WS/Testnet)

## Propósito

Adapters robustos y testeables hacia Bybit: datos históricos (Fase 03), tiempo real (Fase 04) y ejecución Testnet (Fase 12). Producción NUNCA como fuente de ejecución; Testnet nunca para medir rentabilidad.

## Cuándo usar

- Descargar candles históricas ETHUSDT/BTCUSDT 15m/1h/4h.
- Mantener order book local vía WS con snapshots+deltas y reconciliación de secuencia.
- Ciclo de órdenes en Testnet: crear/cancelar/fills/estados.
- Grabar fixtures reales para tests offline.

**Cuándo NO:** lógica de trading/riesgo (dominio puro); simulaciones (backtesting/paper-engine).

## Contratos clave

- REST v5: paginación por cursor para históricos; respetar rate limits (backoff exponencial + jitter).
- WS público (market) vs privado (trade): keepalive/ping, resubscribe tras reconexión.
- Order book: snapshot inicial → deltas con validación de `seq`/`u`; desincronizado ⇒ STALE + rebuild snapshot (PRD §14).
- Autenticación Testnet: HMAC firma (api_key, timestamp, recv_window); credenciales SOLO en `.env` (nunca commit).
- Idempotencia de órdenes: orderLinkId propio para reconciliación.

## Checklist — resiliencia obligatoria

1. Reconexión automática con backoff.
2. STALE detection: sin datos frescos ⇒ Market State=STALE ⇒ no hay decisiones nuevas.
3. Reconciliación al reconectar: comparar estado local vs REST (open orders/positions).
4. Rate limit tracking por endpoint.

## Archivos históricos públicos de trades (Medallion Bronze)

- **Fuente:** data center público de Bybit — archivos `.csv.gz` **diarios** por market/symbol; en esta fase **solo trades** (candles no son fuente canónica; la API Kline queda para reconciliación).
- **Descubrimiento de archivos:** listar inventario por fecha/symbol/market, registrar `source_url` exacta; archivar el inventario como evidencia.
- **Preservación raw byte-a-byte:** `download → <file>.csv.gz.part` → `sha256` → `rename(2)` atómico → metadatos (`source_url, symbol, market, date, size, sha256, download_timestamp, schema_version`). Hash existente ≠ recibido ⇒ FAIL CLOSED, nunca sobrescribir; hash coincide ⇒ SKIP (idempotencia).
- **Detección de esquema del archivo:** leer cabecera real de cada archivo antes de parsear; cualquier cambio de columnas/orden ⇒ nueva `schema_version` + transformador adaptado con test, jamás asumir columnas fijas.
- **Versionado de archivo:** el manifiesto Bronze referencia hashes; renombrar/reemplazar un archivo exige nuevo `dataset_id` en Gold.
- **Filtro de split ANTES de la red:** el downloader rechaza rangos fuera de `allowed_split` (M0–M6 = solo `DEVELOPMENT`) aunque el archivo sea públicamente accesible.

## Testing

- Unit: parsers/firmantes con vectores conocidos.
- Integration: contra FIXTURES GRABADOS (mensajes reales capturados una vez y versionados).
- E2E/Testnet manual controlado: solo Fase 12, con evidencia; jamás en CI.
- api-client-standards aplica a todo cliente HTTP.

## Errores comunes

- Confiar en deltas sin validar secuencia (book silenciosamente corrupto).
- Tratar Testnet fills como representativos de liquidez real.
- Reintentos infinitos sin techo ni alerta.

## Referencias

- PRD §13–14, §26. Skills: error-handling-resilience, testing-integration, infra-control (API keys), data-pipeline-quality.
