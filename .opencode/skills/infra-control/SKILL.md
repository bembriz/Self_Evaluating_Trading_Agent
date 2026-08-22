---
name: infra-control
description: Usar cuando haya que instalar paquetes/herramientas/imágenes/MCPs/servicios, cambiar configuración o infraestructura, o cuando surja cualquier Dependency Proposal antes del USER GATE (PRD §11)
---

# infra-control — DISCOVER → PLAN → REPORT → USER GATE → APPLY → VALIDATE → EVIDENCE

## Propósito

Control total humano sobre infraestructura, dependencias y configuración. **Nada se instala ni cambia sin gate explícito del usuario.**

## Cuándo usar

- Cualquier necesidad nueva: paquete Python, CLI, imagen Docker, extensión, MCP, servicio.
- Cambios en `config/*.yaml`, variables de entorno o servicios locales.
- Cuando un test/build falla por falta de una dependencia (NO la instales: inicia este flujo).

**Cuándo NO usar:** comandos de lectura, dry-run, o uso de dependencias ya aprobadas.

## Entradas → Salidas

- **Entradas:** necesidad detectada, alternativas conocidas, contexto de fase.
- **Salidas:** `docs/phases/<XX>/DP-###-*.md` (proposal), decisión del usuario, evidencia APPLY+VALIDATE.

## Checklist

1. **DISCOVER** (solo lectura): qué existe ya (`uv pip list`, `docker images`, skills globales). ¿Se puede resolver sin instalar nada?
2. **PLAN/DRY-RUN**: nada que instale ni modifique entornos. `uv lock` solo resuelve y escribe el lockfile (no instala paquetes); `uv add --dry-run` no existe en uv 0.11; `docker compose config` es lectura pura. Nunca instalación real.
3. **REPORT**: completar `harness/templates/dependency-proposal.md` (problema, alternativas, por qué no interno, seguridad, licencia, rollback). Nombrar `DP-###-<tema>.md` en la fase correspondiente.
4. **USER GATE**: presentar proposal; esperar APPROVED/REJECTED explícito. Agrupar por fase si son varias.
5. **APPLY**: solo entonces ejecutar la instalación/cambio autorizado.
6. **VALIDATE**: healthcheck/import/tests que demuestren que funciona.
7. **EVIDENCE**: registrar todo con `evidence.sh` (dry-run previo, apply, validación).

## Reglas duras

- Pre-GATE: prohibido cualquier comando que muté entorno (instalar, pull, up).
- Si VALIDATE falla post-APPLY: rollback según proposal + blocker en ledger + informe al usuario.
- Instalaciones agrupadas por fase permitidas; una proposal por grupo.

## Errores comunes

- "Es solo dev-dependency": NO, también requiere gate (ver DP-001 aprobada como ejemplo real).
- Omitir rollback: toda proposal sin plan de reversión se rechaza.
- Instalar "de paso" algo extra no declarado en la proposal: prohibido.

## Referencias

- PRD §11 (gestión obligatoria). Ejemplo aprobado: `docs/phases/00/DP-001-harness-dev-dependencies.md`.
- Globales: python-uv, docker-standards, configuration-environments, security-secrets.
