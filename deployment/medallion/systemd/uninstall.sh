#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="medallion-refresh.service"
TIMER_NAME="medallion-refresh.timer"
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
RUNTIME_DIR="${MEDALLION_RUNTIME_DIR:-/opt/seta-medallion}"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    printf 'ERROR: run as root before invoking this uninstaller.\n' >&2
    exit 1
  fi
}

purge_runtime() {
  rm -rf "${RUNTIME_DIR}"
}

main() {
  require_root
  systemctl disable --now medallion-refresh.timer || true
  rm -f "${UNIT_DIR}/${SERVICE_NAME}" "${UNIT_DIR}/${TIMER_NAME}"
  systemctl daemon-reload
  systemctl reset-failed medallion-refresh.service medallion-refresh.timer || true

  if [[ "${1:-}" == "--purge" ]]; then
    purge_runtime
  fi
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
