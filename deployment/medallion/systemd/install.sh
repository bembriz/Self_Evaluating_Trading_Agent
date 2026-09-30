#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="medallion-refresh.service"
TIMER_NAME="medallion-refresh.timer"
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SRC="${SOURCE_DIR}/${SERVICE_NAME}"
TIMER_SRC="${SOURCE_DIR}/${TIMER_NAME}"

rollback() {
  rm -f "${UNIT_DIR}/${SERVICE_NAME}" "${UNIT_DIR}/${TIMER_NAME}"
  systemctl daemon-reload || true
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    printf 'ERROR: run as root before invoking this installer.\n' >&2
    exit 1
  fi
}

validate_sources() {
  for unit in "${SERVICE_SRC}" "${TIMER_SRC}"; do
    if [[ ! -f "${unit}" || ! -r "${unit}" ]]; then
      printf 'ERROR: missing or unreadable unit file: %s\n' "${unit}" >&2
      exit 1
    fi
  done

  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "${SERVICE_SRC}" "${TIMER_SRC}"
  fi
}

main() {
  require_root
  validate_sources

  trap rollback ERR
  install -m 0644 "${SERVICE_SRC}" "${UNIT_DIR}/${SERVICE_NAME}"
  install -m 0644 "${TIMER_SRC}" "${UNIT_DIR}/${TIMER_NAME}"
  systemctl daemon-reload
  systemctl enable --now medallion-refresh.timer
  trap - ERR
}

main "$@"
