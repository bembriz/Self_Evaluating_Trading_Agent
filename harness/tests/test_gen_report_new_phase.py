from pathlib import Path

import gen_report
import ledger as ld
import new_phase


def construir_repo(tmp_path: Path) -> Path:
    raiz = tmp_path / "repo"
    (raiz / ".git").mkdir(parents=True)
    tpl = raiz / "harness" / "templates"
    tpl.mkdir(parents=True)
    plantilla = (
        "# Reporte {{FASE}} — {{TITULO}}\n"
        "Estado {{ESTADO_FASE}} pct {{PCT_FASE}} global {{PCT_GLOBAL}} gate {{GATE_ESTADO}}\n"
        "{{ENTREGABLES_TABLA}}\n"
    )
    (tpl / "reporte-fase.md").write_text(plantilla, encoding="utf-8")
    (tpl / "uat-checklist.md").write_text("# UAT {{FASE}} {{TITULO}}\n", encoding="utf-8")
    return raiz


def construir_ledger(raiz: Path) -> Path:
    data = {
        "meta": {"proyecto": "t", "reglas": {"cap_fase_sin_gate": 0.9}},
        "phases": {},
        "time_log": [],
        "blockers": [],
    }
    for i in range(19):
        pid = f"{i:02d}"
        n = 2 if i == 0 else 1
        ents = [
            {
                "id": f"d{pid}_{j}",
                "descripcion": f"desc {pid} {j}",
                "estado": "done" if (i == 0 and j == 0) else "pending",
                "evidencia": ["AGENTS.md"] if (i == 0 and j == 0) else [],
            }
            for j in range(n)
        ]
        data["phases"][pid] = {
            "titulo": f"Fase {pid}",
            "estado": "pending",
            "iniciada": None,
            "cerrada": None,
            "entregables": ents,
            "gate_fase": {"estado": "pending", "solicitado": None, "resuelto": None},
        }
    ruta = raiz / "harness" / "state" / "progress.yaml"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ld.save_ledger(data, ruta)
    return ruta


def test_gen_report_rellena_placeholders(tmp_path, monkeypatch, capsys):
    raiz = construir_repo(tmp_path)
    ledger_path = construir_ledger(raiz)
    monkeypatch.setattr(gen_report, "REPO", raiz)
    monkeypatch.setattr(gen_report, "TEMPLATE", raiz / "harness" / "templates" / "reporte-fase.md")
    rc = gen_report.main(["--phase", "00", "--ledger", str(ledger_path)])
    assert rc == 0
    reporte = raiz / "docs" / "phases" / "phase-00-report.md"
    contenido = reporte.read_text(encoding="utf-8")
    assert "{{FASE}}" not in contenido
    assert "# Reporte 00 — Fase 00" in contenido
    assert "`d00_0`" in contenido
    assert "✅ done" in contenido
    assert "⏳ pending" in contenido
    assert capsys.readouterr().out.startswith("Reporte generado")

    rc2 = gen_report.main(["--phase", "00", "--ledger", str(ledger_path)])
    assert rc2 == 1
    assert "No se sobrescribió" in capsys.readouterr().out

    rc3 = gen_report.main(["--phase", "00", "--ledger", str(ledger_path), "--force"])
    assert rc3 == 0


def test_new_phase_scaffold_idempotente(tmp_path, monkeypatch):
    raiz = construir_repo(tmp_path)
    ledger_path = construir_ledger(raiz)
    monkeypatch.setattr(new_phase, "REPO", raiz)
    monkeypatch.setattr(gen_report, "REPO", raiz)
    monkeypatch.setattr(gen_report, "TEMPLATE", raiz / "harness" / "templates" / "reporte-fase.md")

    rc = new_phase.main(["--phase", "01", "--ledger", str(ledger_path)])
    assert rc == 0
    assert (raiz / "docs/phases/01/evidence").is_dir()
    uat = raiz / "docs/uat/phase-01-uat.md"
    assert uat.exists() and "{{FASE}}" not in uat.read_text(encoding="utf-8")
    assert (raiz / "docs/phases/phase-01-report.md").exists()
    data = ld.load_ledger(ledger_path)
    assert data["phases"]["01"]["estado"] == "in_progress"

    segunda = new_phase.main(["--phase", "01", "--ledger", str(ledger_path)])
    assert segunda == 0

    rc18 = new_phase.main(["--phase", "05", "--ledger", str(ledger_path)])
    assert rc18 == 0
    assert (raiz / "docs/phases/05/evidence").is_dir()
