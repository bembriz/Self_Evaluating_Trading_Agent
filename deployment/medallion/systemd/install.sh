#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="medallion-refresh.service"
TIMER_NAME="medallion-refresh.timer"
UNIT_DIR="${SYSTEMD_UNIT_DIR:-/etc/systemd/system}"
RUNTIME_DIR="${MEDALLION_RUNTIME_DIR:-/opt/seta-medallion}"
SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SOURCE_DIR}/../../.." && pwd)"
RUNTIME_SRC="${REPO_ROOT}/src"
SERVICE_SRC="${SOURCE_DIR}/${SERVICE_NAME}"
TIMER_SRC="${SOURCE_DIR}/${TIMER_NAME}"
created_runtime=0

rollback() {
  rm -f "${UNIT_DIR}/${SERVICE_NAME}" "${UNIT_DIR}/${TIMER_NAME}"
  if [[ "${created_runtime}" -eq 1 ]]; then
    rm -rf "${RUNTIME_DIR}"
  fi
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
  if [[ ! -d "${RUNTIME_SRC}" ]]; then
    printf 'ERROR: missing runtime source directory: %s\n' "${RUNTIME_SRC}" >&2
    exit 1
  fi

  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "${SERVICE_SRC}" "${TIMER_SRC}"
  fi
}

deploy_runtime() {
  if [[ ! -d "${RUNTIME_DIR}" ]]; then
    created_runtime=1
  fi
  install -d -m 0755 "${RUNTIME_DIR}"
  rm -rf "${RUNTIME_DIR}/src"
  cp -a "${RUNTIME_SRC}" "${RUNTIME_DIR}/src"
  find "${RUNTIME_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} +
  if [[ "${EUID}" -eq 0 ]]; then
    chown -R root:root "${RUNTIME_DIR}"
  fi
  find "${RUNTIME_DIR}" -type d -exec chmod 0755 {} +
  find "${RUNTIME_DIR}" -type f -exec chmod 0644 {} +
}

install_units() {
  install -m 0644 "${SERVICE_SRC}" "${UNIT_DIR}/${SERVICE_NAME}"
  install -m 0644 "${TIMER_SRC}" "${UNIT_DIR}/${TIMER_NAME}"
}

main() {
  require_root
  validate_sources

  trap rollback ERR
  deploy_runtime
  install_units
  systemctl daemon-reload
  systemctl enable --now medallion-refresh.timer
  trap - ERR
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
