"""Tests del drill de safeguards (harness/scripts/safeguard_drill.py, Task 6).

Ejercitan las secuencias completas de los guards REALES del dominio puro del
producto (kill switch y daily loss) tal y como las consulta el Risk Engine, la
forma de la evidencia JSON, la escritura crash-safe y el exit code del CLI.

Fidelidad al producto (file:line):
- Kill switch: guards.py KillSwitch/KillSwitchState/allows_trading/activate/reset.
- BUY rechazado: RiskEngine.evaluate rechaza primero por kill_switch
  (domain/risk/engine.py:66-69) y el daily loss solo en la rama BUY
  (engine.py:81-83); SELL reduce no consulta daily loss (engine.py:75-79).
- Persistencia del daily loss entre reinicios = re-derivación por replay de los
  fills persistidos del día (recovery.py:37-50 + paper_runner.replay), no un
  flag serializado; el reset por rollover UTC = cruce de utc_day_index en
  PaperEngine.on_price (paper_engine.py:141-146).
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import safeguard_drill as sd

BASE_MS = 1_700_000_000_000  # dentro del día UTC 19675 (evita colisión de borde)

KILL_SWITCH_STEPS = [
    "activate",
    "buy_rejected",
    "persist",
    "restart_still_active",
    "buy_still_rejected",
    "operator_reset",
]
DAILY_LOSS_STEPS = [
    "daily_loss_exceeded",
    "buy_rejected",
    "sell_allowed",
    "restart_persists",
    "utc_rollover_reset",
]

ARTIFACT = {
    "git_commit": "906556371d072da2e7aa47a0ed780c2f61badc3d",
    "application_version": "0.1.3",
    "docker_image_digest": (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    ),
    "strategy_version": "baseline-v1",
    "risk_config_version": "risk-v1",
}


def test_canonical_step_tokens_mirror_producer() -> None:
    """Los tokens del drill son exactamente las secuencias canónicas del productor."""
    assert list(sd.KILL_SWITCH_STEPS) == KILL_SWITCH_STEPS
    assert list(sd.DAILY_LOSS_STEPS) == DAILY_LOSS_STEPS


def test_kill_switch_full_sequence_passes() -> None:
    steps = sd.run_kill_switch_drill(base_ms=BASE_MS)

    assert [s.step for s in steps] == KILL_SWITCH_STEPS
    assert all(s.ok for s in steps), [(s.step, s.detail) for s in steps if not s.ok]
    assert sd.sequence_passed("kill_switch", steps)

    details = {s.step: s.detail for s in steps}
    assert "kill_switch" in details["buy_rejected"]
    assert "kill_switch" in details["buy_still_rejected"]
    assert "human" in details["operator_reset"]


def test_kill_switch_evidence_shape_and_crash_safe_write(tmp_path: Path) -> None:
    steps = sd.run_kill_switch_drill(base_ms=BASE_MS)
    entry = sd.build_evidence_entry(
        "kill_switch", steps, artifact=ARTIFACT, at_iso="2026-09-09T12:00:00Z"
    )

    assert entry["type"] == "kill_switch"
    assert entry["status"] == "PASS"
    assert entry["at_iso"] == "2026-09-09T12:00:00Z"
    assert entry["steps"] == KILL_SWITCH_STEPS
    assert entry["artifact"] == ARTIFACT

    path = tmp_path / "safeguard-evidence.json"
    sd.write_evidence_crash_safe(path, {"kill_switch": entry})
    assert not path.with_name(path.name + ".tmp").exists()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == {"kill_switch": entry}

    # Una segunda escritura con el otro kind preserva la entrada previa.
    daily_steps = sd.run_daily_loss_drill(base_ms=BASE_MS)
    daily_entry = sd.build_evidence_entry(
        "daily_loss", daily_steps, artifact=ARTIFACT, at_iso="2026-09-09T12:01:00Z"
    )
    sd.write_evidence_crash_safe(path, {"kill_switch": entry, "daily_loss": daily_entry})
    assert not path.with_name(path.name + ".tmp").exists()
    merged = json.loads(path.read_text(encoding="utf-8"))
    assert merged["kill_switch"]["status"] == "PASS"
    assert merged["daily_loss"]["status"] == "PASS"


def test_daily_loss_full_sequence_and_utc_rollover() -> None:
    steps = sd.run_daily_loss_drill(base_ms=BASE_MS)

    assert [s.step for s in steps] == DAILY_LOSS_STEPS
    assert all(s.ok for s in steps), [(s.step, s.detail) for s in steps if not s.ok]
    assert sd.sequence_passed("daily_loss", steps)

    details = {s.step: s.detail for s in steps}
    assert "max_daily_loss" in details["buy_rejected"]
    assert "reduce" in details["sell_allowed"]
    assert "replay" in details["restart_persists"]
    assert "utc_day_index" in details["utc_rollover_reset"]


def test_daily_loss_uses_restart_persistence_semantics_of_product() -> None:
    """El restart conserva el daily loss por re-derivación (replay), no por flag.

    Simula el corte de proceso: los fills del día son la única fuente persistida
    (recovery.py carga solo el kill switch; el daily loss se re-deriva replanteando
    velas). El drill debe reconstruir el mismo acumulador desde esos fills.
    """
    steps = sd.run_daily_loss_drill(base_ms=BASE_MS)
    restart = next(s for s in steps if s.step == "restart_persists")
    rollover = next(s for s in steps if s.step == "utc_rollover_reset")
    assert restart.ok
    assert (
        "no serializa" in restart.detail
        or "re-deriva" in restart.detail
        or "replay" in restart.detail
    )
    assert rollover.ok
    assert "resetea" in rollover.detail


def test_incomplete_sequence_is_not_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un paso que falla (guard que NO rechaza el BUY) ⇒ secuencia NO pasa."""

    class AlwaysApproveEngine:
        def __init__(self, config: object) -> None:
            self.config = config

        def evaluate(self, proposal: object, state: object) -> SimpleNamespace:
            return SimpleNamespace(
                approved=True, reason="ok", size=None, stop_loss=None, take_profit=None
            )

    monkeypatch.setattr(sd, "RiskEngine", AlwaysApproveEngine)
    steps = sd.run_kill_switch_drill(base_ms=BASE_MS)

    assert not sd.sequence_passed("kill_switch", steps)
    assert not all(s.ok for s in steps)
    entry = sd.build_evidence_entry(
        "kill_switch", steps, artifact=ARTIFACT, at_iso="2026-09-09T12:00:00Z"
    )
    assert entry["status"] == "FAIL"


def test_load_evidence_absent_and_corrupt(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert sd.load_evidence(missing) == {}

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        sd.load_evidence(corrupt)


def test_cli_exit_zero_and_writes_evidence_on_pass(tmp_path: Path) -> None:
    scripts = Path(sd.__file__).resolve().parent
    out = tmp_path / "safeguard-evidence.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(scripts / "safeguard_drill.py"),
            "--kind",
            "kill_switch",
            "--out",
            str(out),
            "--now-ms",
            str(BASE_MS),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["kill_switch"]["status"] == "PASS"
    assert data["kill_switch"]["steps"] == KILL_SWITCH_STEPS
    assert not out.with_name(out.name + ".tmp").exists()
