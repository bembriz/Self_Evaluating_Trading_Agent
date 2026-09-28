# deployment/platform — fundación de plataforma compartida (Medallion M2)

Base mínima de configuración para la plataforma compartida en lenovosrv.
Fuentes de diseño: [ADR-0006](../../docs/adr/ADR-0006-shared-platform-lenovosrv.md) y
`docs/design/medallion-replay-architecture.md` (§ storage y § redes).

## Qué existe ya en lenovosrv (creado en M2, sin migrar nada)

| Recurso | Detalle |
|---|---|
| `/srv/docker/platform/` | directorio raíz de futuros servicios de plataforma |
| `/srv/fast/medallion/{cache,replay-work,tmp,indexes}` | caché desechable sobre **NVMe** (reproducible; borrarla nunca destruye el canónico) |
| `/srv/data/{medallion,gastosia,backups}` | datos canónicos sobre **HDD** `LENOVO_DATA` (`/dev/sda1`, UUID `10fff707-60e4-4321-afa0-a3c4704d9e8d`, marker `/srv/data/.lenovosrv-data-volume`) |
| red externa `platform-net` | bridge, **0 contenedores conectados** al crearse (evidencia `docs/phases/23/evidence/m2-03-network.log`) |

## platform-net

- Red **externa** (`external: true`): el compose de cada solución la referencia sin crearla.
- Solo se conecta quien necesite infraestructura compartida (regla § redes del design doc).
- `platform-caddy` (futuro) será el único publicador de 80/443; **PostgreSQL jamás expuesto públicamente**.
- Cada solución conserva su red privada por defecto.

## Reglas de uso

1. **Ningún servicio se migra** (postgres, prometheus, grafana, caddy) sin gate explícito;
   la certificación paper vigente no se interrumpe.
2. `compose.yaml` usa `profiles: ["platform"]`: `docker compose up` sin perfil no arranca nada.
3. `platform-postgres` es un plano futuro: un motor, una BD y un rol por solución (least privilege).
4. Storage: HDD (`/srv/data`) canónico · NVMe (`/srv/fast`) caché desechable y reproducible.
5. Secrets por variables de entorno (`PLATFORM_PG_PASSWORD`), nunca en el repo.
