from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = ROOT / "deployment" / "medallion" / "systemd"
SERVICE = SYSTEMD_DIR / "medallion-refresh.service"
TIMER = SYSTEMD_DIR / "medallion-refresh.timer"
INSTALL = SYSTEMD_DIR / "install.sh"
UNINSTALL = SYSTEMD_DIR / "uninstall.sh"

RUNTIME_DIR = "/opt/seta-medallion"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )


def _run_sandboxed(
    unit_dir: Path, runtime_dir: Path, script: str
) -> subprocess.CompletedProcess[str]:
    env = f"SYSTEMD_UNIT_DIR={unit_dir} MEDALLION_RUNTIME_DIR={runtime_dir}"
    return _run_bash(f"env {env} bash -c {_quote(script)}")


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
    assert "from infrastructure.medallion.split_guard import IngestScope" in text
    assert "capacity_guard=CapacityGuardConfig()" in text
    assert "ingest_scope=IngestScope(" in text
    assert "run_refresh(cfg)" in text
    assert "ExecStart=" in text
    assert "paper" not in text.lower()
    assert "certification" not in text.lower()


def test_service_execstart_python_payload_compiles() -> None:
    import re

    text = _read(SERVICE)
    match = re.search(r'ExecStart=/usr/bin/python3 -c "(.*)"\s*$', text, re.M)
    assert match is not None, "ExecStart python payload not found"
    compile(match.group(1), "<execstart>", "exec")


def test_service_runtime_path_schedule_bronze_and_scope() -> None:
    text = _read(SERVICE)

    assert f"WorkingDirectory={RUNTIME_DIR}" in text
    assert f"Environment=PYTHONPATH={RUNTIME_DIR}/src" in text
    assert "Environment=MEDALLION_START_DAY=2026-08-24" in text
    assert "Environment=MEDALLION_INGEST_SCOPE=DEVELOPMENT_AND_FUTURE_COLLECTION" in text
    assert "/srv/data/medallion/bronze/bybit/spot/ETHUSDT" in text
    assert "'/srv/data/medallion/bronze/bybit/spot'" not in text


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


def test_install_script_deploys_runtime_and_is_idempotent(tmp_path: Path) -> None:
    unit_dir = tmp_path / "units"
    runtime_dir = tmp_path / "runtime"
    unit_dir.mkdir()
    script = f"""
set -euo pipefail
source {INSTALL}
deploy_runtime
test -f {runtime_dir}/src/infrastructure/medallion/refresh.py
test -f {runtime_dir}/src/infrastructure/medallion/capacity_guards.py
test -f {runtime_dir}/src/infrastructure/medallion/split_guard.py
test "$(stat -c %a {runtime_dir}/src/infrastructure/medallion)" = "755"
test "$(stat -c %a {runtime_dir}/src/infrastructure/medallion/refresh.py)" = "644"
deploy_runtime
test -f {runtime_dir}/src/infrastructure/medallion/refresh.py
echo IDEMPOTENT_OK
"""
    result = _run_sandboxed(unit_dir, runtime_dir, script)

    assert result.returncode == 0, result.stderr
    assert "IDEMPOTENT_OK" in result.stdout
    assert not list(runtime_dir.rglob("*.pyc"))


def test_install_script_rollback_removes_units_and_created_runtime(tmp_path: Path) -> None:
    unit_dir = tmp_path / "units"
    runtime_dir = tmp_path / "runtime"
    unit_dir.mkdir()
    script = f"""
set -euo pipefail
source {INSTALL}
created_runtime=1
rollback
test ! -e {runtime_dir}
test ! -e {unit_dir}/medallion-refresh.service
echo ROLLBACK_OK
"""
    result = _run_sandboxed(unit_dir, runtime_dir, script)

    assert result.returncode == 0, result.stderr
    assert "ROLLBACK_OK" in result.stdout


def test_uninstall_script_disables_removes_and_reloads_safely() -> None:
    text = _read(UNINSTALL)

    assert "set -euo pipefail" in text
    assert "systemctl disable --now medallion-refresh.timer" in text
    assert "rm -f" in text
    assert "systemctl daemon-reload" in text
    assert "systemctl reset-failed" in text
    assert "sudo" not in text


def test_uninstall_purge_removes_runtime_only_when_requested(tmp_path: Path) -> None:
    unit_dir = tmp_path / "units"
    runtime_dir = tmp_path / "runtime"
    unit_dir.mkdir()
    runtime_dir.mkdir()
    (runtime_dir / "src").mkdir()
    script = f"""
set -euo pipefail
source {UNINSTALL}
purge_runtime
test ! -e {runtime_dir}
echo PURGE_OK
"""
    result = _run_sandboxed(unit_dir, runtime_dir, script)

    assert result.returncode == 0, result.stderr
    assert "PURGE_OK" in result.stdout


def _quote(script: str) -> str:
    return "'" + script.replace("'", "'\"'\"'") + "'"
