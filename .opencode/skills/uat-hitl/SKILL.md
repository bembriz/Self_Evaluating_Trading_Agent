---
name: uat-hitl
description: Usar cuando una fase o entregable requiera validación por el usuario humano (HITL), al preparar instructivos UAT con pasos y resultados esperados, o al registrar veredictos APPROVED/REJECTED (PRD §74)
---

# uat-hitl — UAT Human-in-the-Loop

## Propósito

El usuario es el único que puede aprobar UAT. Esta skill define cómo preparar un instructivo ejecutable paso a paso, qué evidencia recolectar y cómo registrar el veredicto.

## Cuándo usar

- Al cerrar scope de fase (UAT es requisito de gate PRD §77).
- Cuando una funcionalidad necesita validación humana subjetiva (dashboard, flujos CLI).
- Ante cualquier decisión HITL: aprobaciones, mejoras de estrategia, LIVE.

**Cuándo NO usar:** verificaciones automatizables (esas van a tests + evidencia).

## Entradas → Salidas

- **Entradas:** funcionalidad terminada, comandos reproducibles, datos/fixtures necesarios.
- **Salidas:** `docs/uat/phase-XX-uat.md` completado con veredicto `VEREDICTO UAT: APPROVED|REJECTED`.

## Checklist de preparación

1. Copia plantilla: `harness/templates/uat-checklist.md` → `docs/uat/phase-XX-uat.md` (`new_phase.py` lo hace).
2. Precondiciones verificables (servicios arriba, dataset presente, versión).
3. Pasos numerados: acción EXACTA (comando copiable) + resultado esperado observable.
4. Incluye casos negativos si aplican (p.ej. "kill switch activo bloquea órdenes").
5. Define evidencia a adjuntar (captura/salida) por paso.
6. NO rellenes "Resultado observado" ni el veredicto: son del usuario.

## Registro del veredicto

- El usuario sustituye `VEREDICTO UAT: PENDING` por `APPROVED` o `REJECTED`.
- `gate_check.py` busca el literal `VEREDICTO UAT: APPROVED` para dar PASS.
- Si REJECTED: registrar motivo como blocker en ledger y volver al ciclo de la fase.

## Errores comunes

- Pasos ambiguos ("probar la API"): deben ser comandos exactos.
- Aprobar "en nombre del usuario": PROHIBIDO (PRD §74).
- UAT sin precondiciones: irreproducible.

## Referencias

- Plantilla: `harness/templates/uat-checklist.md`. PRD §74. Global: superpowers:verification-before-completion.
