# Reporte de Fase 12 — Bybit Testnet

**Fecha:** 2026-08-24
**Estado de fase:** in_progress (pendiente UAT + gate)
**Avance fase:** 100.0% entregables con evidencia · **Gate mecánico:** 5 PASS · 0 FAIL · 2 MANUAL

---

## 1. Executive Summary

Adaptador de ejecución Bybit Testnet completo (PRD §26; skill bybit-integration): firmante HMAC-SHA256 v5 verificado con vectores conocidos, creación/cancelación de órdenes spot con `order_link_id` propio (idempotencia), parseo tolerante de órdenes remotas, reconciliación local↔exchange que detecta desconocidas/desactualizadas/diferencias de estado, manejo de retCode y 429/5xx con backoff limitado + Retry-After, y supervisor de conexión con backoff exponencial acotado y gancho on_reconnect. Suite 353 passed, cobertura 93.35%.

## 2. Objetivo

Ciclo de órdenes en Testnet: crear/cancelar/fills/estados, errores/rate limiting, reconciliación al reconectar y recovery de desconexiones (PRD §79 Fase 12). Testnet jamás para medir rentabilidad.

## 3. Scope

- `domain/trading/order.py`: OrderRequest (orderLinkId autogenerado), OrderStatus con estados terminales, TrackedOrder con transiciones validadas.
- `infrastructure/bybit/auth.py`: BybitSigner HMAC (timestamp+key+recvWindow+path+payload) y BybitCredentials desde .env.
- `infrastructure/bybit/trade_client.py`: place_order/cancel_order (idempotente ante orden inexistente)/open_orders; RemoteOrder pydantic tolerante; reintentos 429/5xx.
- `application/services/reconciliation.py`: ReconciliationReport (unknown_remote/stale_local/status_diffs).
- `application/services/connection_supervisor.py`: backoff exponencial acotado + on_reconnect.

## 4. Out of Scope
- Validación contra Testnet real con API keys (UAT manual opcional; jamás en CI).
- WS privado de trade (fills por push): los fills llegan vía reconciliación REST; push en fase posterior si se requiere.
- Ejecución LIVE (permanentemente deshabilitada por defecto, PRD §49).

## 21. Git diff

> Resumen del diff + referencia al diff completo generado para el Commit Candidate Report.

## 22. Riesgos

> Riesgos introducidos o descubiertos y su mitigación.

## 23. Seguridad

> Revisión de secretos, superficies expuestas, permisos.

## 24. Deuda técnica

> Deuda conocida registrada en esta fase.

## 25. Known Issues

> Problemas conocidos no bloqueantes.

## 26. Rollback

> Cómo revertir los cambios de esta fase.

## 27. Competencias de Ingeniería de Software practicadas

> Mapear contra PRD §80: qué se practicó y dónde.

## 28. Definition of Done

> Checklist §77: scope complete / tests PASS / integration PASS / E2E PASS / UAT approved /
> coverage ≥90% / CI green / lint green / typing green / documentation complete /
> evidence complete / diff reviewed / user approved.

## 29. Estado CI

> Estado del pipeline (o justificación si aún no existe remoto).

## 30. Solicitud de aprobación

- [ ] Presentado al usuario
- **DECISIÓN DEL USUARIO:** ☒ APPROVED ☐ REJECTED
- Comentario:
