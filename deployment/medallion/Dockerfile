# seta-medallion — runtime batch/one-shot del pipeline Medallion (Fase 23 · M8)
#
# Contexto de build = raíz del repo (deployment/medallion/compose.yaml → context: ../..).
# Sin dependencias de terceros: los 5 CLIs Medallion son stdlib puro (Python 3.12),
# por lo que NO hay `pip install`, NO se copian secretos/.env y solo se lleva `src/`.
FROM python:3.12-slim

# Fail-closed: la imagen debe quedar ligada al SHA exacto del repositorio.
ARG GIT_SHA
RUN echo "$GIT_SHA" | grep -Eq '^[0-9a-f]{40}$' \
    || { echo "FALLO: GIT_SHA ausente/inválido (se espera sha1 de 40 hex): '$GIT_SHA'" >&2; exit 1; }

LABEL org.opencontainers.image.title="seta-medallion" \
      org.opencontainers.image.description="Self-Evaluating Trading Agent — Medallion batch runtime (one-shot)" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.base.name="docker.io/library/python:3.12-slim"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    MEDALLION_GIT_SHA="${GIT_SHA}"

WORKDIR /app
COPY src ./src
RUN printf '%s\n' "$GIT_SHA" > /app/GIT_SHA && chmod 444 /app/GIT_SHA

# Sin puertos ni healthcheck: contenedor one-shot, no daemon.
USER 1000:1000
CMD ["python3", "-m", "infrastructure.medallion.replay_cli", "--help"]
