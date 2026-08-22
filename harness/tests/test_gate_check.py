import json
from pathlib import Path

import gate_check as gc
import ledger as ld
from conftest import make_entregable


def preparar_fase(root: Path, done=True, evidencia_ok=True, coverage=None, umbral=90.0):
    (root / ".git").mkdir(parents=True, exist_ok=True)
    ev_dir = root / "docs" / "phases" / "00" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    if coverage is not None:
        (ev_dir / "coverage.json").write_text(
            json.dumps({"totals": {"percent_covered": coverage}}), encoding="utf-8"
        )
    (ev_dir / "lint.log").write_text("comando: ruff\nexit=0\n", encoding="utf-8")
    (ev_dir / "typing.log").write_text("comando: mypy\nexit=0\n", encoding="utf-8")
    uat = root / "docs" / "uat" / "phase-00-uat.md"
    uat.parent.mkdir(parents=True, exist_ok=True)
    uat.write_text("## VEREDICTO UAT: APPROVED\n", encoding="utf-8")

    data = {
        "meta": {
            "proyecto": "t",
            "reglas": {"cap_fase_sin_gate": 0.9, "coverage_minima_por_fase": {"00": umbral}},
        },
        "phases": {},
        "time_log": [],
        "blockers": [],
    }
    for i in range(19):
        pid = f"{i:02d}"
        ents = []
        for j in range(2 if i == 0 else 1):
            eid = f"d{pid}_{j}"
            estado = "done" if (done or pid != "00") else "pending"
            if estado == "done":
                ruta = f"{eid}.log" if evidencia_ok else f"falta/{eid}.log"
                ents.append(make_entregable(eid, "done", [f"docs/phases/00/evidence/{ruta}"]))
                if evidencia_ok:
                    (root / "docs/phases/00/evidence" / f"{eid}.log").touch()
            else:
                ents.append(make_entregable(eid))
        data["phases"][pid] = {
            "titulo": f"F{pid}",
            "estado": "in_progress",
            "iniciada": None,
            "cerrada": None,
            "entregables": ents,
            "gate_fase": {
                "estado": "approved" if (done and pid == "00") else "pending",
                "solicitado": None,
                "resuelto": None,
            },
        }
    return data


def test_todo_en_orden_da_todos_pass(tmp_path):
    data = preparar_fase(tmp_path, coverage=92.0)
    checks = gc.run_checks(tmp_path, data, "00")
    p, f, m = gc.summarize(checks)
    assert (p, f, m) == (7, 0, 0)


def test_pendientes_dan_fail_en_scope(tmp_path):
    data = preparar_fase(tmp_path, done=False)
    checks = gc.run_checks(tmp_path, data, "00")
    por_id = {c["id"]: c for c in checks}
    assert por_id["scope-complete"]["estado"] == "FAIL"


def test_evidencia_faltante_dan_fail(tmp_path):
    data = preparar_fase(tmp_path, done=True, evidencia_ok=False)
    checks = gc.run_checks(tmp_path, data, "00")
    por_id = {c["id"]: c for c in checks}
    assert por_id["scope-complete"]["estado"] == "PASS"
    assert por_id["evidence-files"]["estado"] == "FAIL"


def test_coverage_bajo_umbral_fail_y_manual_sin_archivo(tmp_path):
    data = preparar_fase(tmp_path, coverage=75.0, umbral=80.0)
    checks = gc.run_checks(tmp_path, data, "00")
    cov = {c["id"]: c for c in checks}["coverage-gate"]
    assert cov["estado"] == "FAIL"

    (tmp_path / "docs/phases/00/evidence/coverage.json").unlink()
    checks = gc.run_checks(tmp_path, data, "00")
    cov = {c["id"]: c for c in checks}["coverage-gate"]
    assert cov["estado"] == "MANUAL"


def test_coverage_json_corrupto_es_manual(tmp_path):
    data = preparar_fase(tmp_path, coverage=95.0)
    (tmp_path / "docs/phases/00/evidence/coverage.json").write_text("{roto", encoding="utf-8")
    checks = gc.run_checks(tmp_path, data, "00")
    cov = {c["id"]: c for c in checks}["coverage-gate"]
    assert cov["estado"] == "MANUAL"


def test_lint_log_sin_exit_cero_es_fail(tmp_path):
    data = preparar_fase(tmp_path, coverage=90.0)
    (tmp_path / "docs/phases/00/evidence/lint.log").write_text("exit=1\n", encoding="utf-8")
    checks = gc.run_checks(tmp_path, data, "00")
    lint = {c["id"]: c for c in checks}["lint-green"]
    assert lint["estado"] == "FAIL"


def test_uat_pendiente_es_manual(tmp_path):
    data = preparar_fase(tmp_path, coverage=90.0)
    (tmp_path / "docs/uat/phase-00-uat.md").write_text("VEREDICTO UAT: PENDING", encoding="utf-8")
    checks = gc.run_checks(tmp_path, data, "00")
    uat = {c["id"]: c for c in checks}["uat-approved"]
    assert uat["estado"] == "MANUAL"


def test_render_y_exit_codes(tmp_path, capsys):
    data = preparar_fase(tmp_path, coverage=91.0)
    checks = gc.run_checks(tmp_path, data, "00")
    texto = gc.render(checks, "00", "Fase 00")
    assert "7 PASS · 0 FAIL · 0 MANUAL" in texto
    assert "puede solicitarse al usuario" in texto

    data_mal = preparar_fase(tmp_path / "otro", done=False)
    checks_mal = gc.run_checks(tmp_path / "otro", data_mal, "00")
    p, f, m = gc.summarize(checks_mal)
    assert f > 0
    assert gc.render(checks_mal, "00", "x").count("**") > 0


def test_record_approval_bloqueado_por_fail(tmp_path, capsys):
    ledger_path = tmp_path / "l.yaml"
    data = preparar_fase(tmp_path, done=False)
    ld.save_ledger(data, ledger_path)
    rc = gc.main(["--phase", "00", "--ledger", str(ledger_path), "--record-approval"])
    assert rc == 2
    assert "FAIL" in capsys.readouterr().err


def test_record_approval_bloqueado_por_manual(tmp_path, capsys):
    ledger_path = tmp_path / "l.yaml"
    data = preparar_fase(tmp_path, coverage=None)
    ld.save_ledger(data, ledger_path)
    rc = gc.main(["--phase", "00", "--ledger", str(ledger_path), "--record-approval"])
    assert rc == 3
    assert "MANUAL" in capsys.readouterr().err


def test_record_approval_registra_cuando_todo_verde(tmp_path, capsys):
    ledger_path = tmp_path / "l.yaml"
    data = preparar_fase(tmp_path, coverage=93.0)
    ld.save_ledger(data, ledger_path)
    rc = gc.main(["--phase", "00", "--ledger", str(ledger_path), "--record-approval"])
    assert rc == 0
    fase = ld.load_ledger(ledger_path)["phases"]["00"]
    assert fase["gate_fase"]["estado"] == "approved"


def test_main_sin_record_devuelve_1_con_fail(tmp_path):
    ledger_path = tmp_path / "l.yaml"
    data = preparar_fase(tmp_path, done=False)
    ld.save_ledger(data, ledger_path)
    assert gc.main(["--phase", "00", "--ledger", str(ledger_path)]) == 1
