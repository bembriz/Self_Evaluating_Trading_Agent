#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="medallion-refresh.service"
TIMER_NAME="medallion-refresh.timer"
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    printf 'ERROR: run as root before invoking this uninstaller.\n' >&2
    exit 1
  fi
}

main() {
  require_root
  systemctl disable --now medallion-refresh.timer || true
  rm -f "${UNIT_DIR}/${SERVICE_NAME}" "${UNIT_DIR}/${TIMER_NAME}"
  systemctl daemon-reload
  systemctl reset-failed medallion-refresh.service medallion-refresh.timer || true
}

main "$@"
