#!/usr/bin/env bash
# evidence.sh — Envuelve un comando, guarda su salida como evidencia auditable.
#
# Uso: evidence.sh <fase> <nombre-evidencia> -- <comando...>
# Efecto:
#   docs/phases/<fase>/evidence/<nombre>.log   (salida completa del comando)
#   docs/phases/<fase>/evidence/log.md         (índice con fecha, comando, exit code)
# Propaga el exit code del comando envuelto.
set -u

if [ "$#" -lt 3 ]; then
  echo "uso: $0 <fase> <nombre-evidencia> -- <comando...>" >&2
  exit 64
fi

FASE="$1"; NOMBRE="$2"; shift 2
[ "${1:-}" = "--" ] && shift || { echo "se requiere '--' antes del comando" >&2; exit 64; }

RAIZ="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DIR="$RAIZ/docs/phases/$FASE/evidence"
mkdir -p "$DIR"
LOG="$DIR/$NOMBRE.log"

{
  echo "# evidencia: $NOMBRE"
  echo "fecha: $(date -Iseconds)"
  echo "fase: $FASE"
  echo "comando: $*"
} >"$LOG"

"$@" >>"$LOG" 2>&1
EXIT=$?
echo "exit=$EXIT" >>"$LOG"

REGISTRO="- \`$(date -Iseconds)\` **$NOMBRE** → \`$*\` · exit=\`$EXIT\` · artifact: docs/phases/$FASE/evidence/$NOMBRE.log"
touch "$DIR/log.md"
printf '%s\n' "$REGISTRO" >>"$DIR/log.md"

echo "[evidence] $NOMBRE registrado (exit=$EXIT) en docs/phases/$FASE/evidence/"
exit $EXIT
