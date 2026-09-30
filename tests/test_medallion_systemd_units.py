from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = ROOT / "deployment" / "medallion" / "systemd"
SERVICE = SYSTEMD_DIR / "medallion-refresh.service"
TIMER = SYSTEMD_DIR / "medallion-refresh.timer"
INSTALL = SYSTEMD_DIR / "install.sh"
UNINSTALL = SYSTEMD_DIR / "uninstall.sh"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_timer_runs_daily_at_0620_utc_with_persistence_and_jitter() -> None:
    text = _read(TIMER)

    assert "OnCalendar=*-*-* 06:20:00 UTC" in text
    assert "Persistent=true" in text
    assert "RandomizedDelaySec=15m" in text
    assert "Unit=medallion-refresh.service" in text
    assert "WantedBy=timers.target" in text


def test_service_is_oneshot_and_delegates_to_existing_refresh() -> None:
    text = _read(SERVICE)

    assert "Type=oneshot" in text
    assert "User=administrador" in text
    assert "Restart=on-failure" in text
    assert "StandardOutput=journal" in text
    assert "StandardError=journal" in text
    assert "from infrastructure.medallion.capacity_guards import CapacityGuardConfig" in text
    assert "from infrastructure.medallion.refresh import RefreshConfig, run_refresh" in text
    assert "capacity_guard=CapacityGuardConfig()" in text
    assert "run_refresh(cfg)" in text
    assert "ExecStart=" in text
    assert "paper" not in text.lower()
    assert "certification" not in text.lower()


def test_install_script_validates_and_enables_only_the_timer() -> None:
    text = _read(INSTALL)

    assert "set -euo pipefail" in text
    assert "systemctl daemon-reload" in text
    assert "systemctl enable --now medallion-refresh.timer" in text
    assert "systemctl enable --now medallion-refresh.service" not in text
    assert "systemctl start medallion-refresh.service" not in text
    assert "systemd-analyze verify" in text
    assert "install -m 0644" in text
    assert "rollback" in text.lower()
    assert "sudo" not in text


def test_uninstall_script_disables_removes_and_reloads_safely() -> None:
    text = _read(UNINSTALL)

    assert "set -euo pipefail" in text
    assert "systemctl disable --now medallion-refresh.timer" in text
    assert "rm -f" in text
    assert "systemctl daemon-reload" in text
    assert "systemctl reset-failed" in text
    assert "sudo" not in text
