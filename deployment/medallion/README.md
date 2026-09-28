# deployment/medallion — runtime Medallion (batch/one-shot) en lenovosrv

Imagen + compose para ejecutar los CLIs Medallion en contenedor, aislados, **sin daemon**
(scheduler ni proceso permanente), sin PostgreSQL, sin platform-net y sin puertos.

| Archivo | Rol |
|---|---|
| `Dockerfile` | `python:3.12-slim` + `COPY src` (CLIs stdlib, sin pip, sin secretos). `ARG GIT_SHA` obligatorio de 40 hex ⇒ `LABEL org.opencontainers.image.revision` + `/app/GIT_SHA`. `USER 1000:1000`. |
| `Dockerfile.dockerignore` | contexto de build limitado a `src/`. |
| `compose.yaml` | servicio `medallion` one-shot: `network_mode: none`, `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, mounts canónico `ro` / NVMe `rw` / marker `ro`, comando = replay M7. |

## Build (requiere las 2 variables)

```bash
export MEDALLION_GIT_SHA=$(git rev-parse HEAD)   # 40 hex
export MEDALLION_IMAGE_TAG=m8-$(git rev-parse --short=12 HEAD)
docker compose -f deployment/medallion/compose.yaml build
```

## Ejecución

```bash
# replay one-shot (ledger → /srv/fast/medallion/replay-work/m8/ledger.jsonl)
docker compose -f deployment/medallion/compose.yaml run --rm medallion

# validar un CLI dentro del contenedor (sin writes)
docker compose -f deployment/medallion/compose.yaml run --rm medallion \
  python3 -m infrastructure.medallion.gold_cli --help
```

`docker compose run --rm` termina y **borra** el contenedor: no queda nada corriendo.

## Despliegue en lenovosrv

Contexto de build espejo (idéntico bit a bit al repo en el SHA del build):

```text
/srv/docker/medallion/
├── .dockerignore
├── Dockerfile.dockerignore          (vía deployment/medallion/)
├── src/
└── deployment/medallion/{Dockerfile,compose.yaml,Dockerfile.dockerignore,README.md}
```

```bash
docker compose -f /srv/docker/medallion/deployment/medallion/compose.yaml build
docker compose -f /srv/docker/medallion/deployment/medallion/compose.yaml run --rm medallion
```

## Invariantes

- HDD canónico `/srv/data` = **solo lectura** durante M8 (tiering ADR-0007).
- Salida de replay = NVMe `/srv/fast/medallion/**` (desechable y reproducible).
- `--require-marker /srv/data/.lenovosrv-data-volume` se valida dentro del contenedor
  (mount ro) — misma protección FAIL-CLOSED que en M7.
- Sin credenciales: el build/run nunca recibe `.env` ni secretos.
