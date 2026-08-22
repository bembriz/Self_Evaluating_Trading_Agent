#!/usr/bin/env python3
"""Scaffold de una fase: directorios de evidencia, checklist UAT, reporte base.

Uso: new_phase.py --phase 01
Idempotente: elementos existentes no se sobrescriben.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger as ld

REPO = ld.find_repo_root()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="new-phase", description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--ledger", default=None)
    args = parser.parse_args(argv)

    data = ld.load_ledger(args.ledger)
    fase = ld.get_phase(data, args.phase)
    pid = args.phase

    ev_dir = REPO / "docs" / "phases" / pid / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)

    uat_dir = REPO / "docs" / "uat"
    uat_dir.mkdir(parents=True, exist_ok=True)
    uat_destino = uat_dir / f"phase-{pid}-uat.md"
    if not uat_destino.exists():
        ruta_tpl = REPO / "harness" / "templates" / "uat-checklist.md"
        plantilla_uat = ruta_tpl.read_text(encoding="utf-8")
        uat_destino.write_text(
            plantilla_uat.replace("{{FASE}}", pid).replace("{{TITULO}}", fase.get("titulo", "")),
            encoding="utf-8",
        )
        print(f"UAT creado: {uat_destino.relative_to(REPO)}")

    reporte_destino = REPO / "docs" / "phases" / f"phase-{pid}-report.md"
    if not reporte_destino.exists():
        import gen_report

        gen_report.main(["--phase", pid])
    else:
        print(f"Reporte ya existe: {reporte_destino.name}")

    if fase.get("estado") == "pending":
        ld.set_phase_status(data, pid, "in_progress")
        ld.save_ledger(data, args.ledger)
        print(f"Fase {pid} → in_progress ({dt.date.today()})")
    else:
        print(f"Fase {pid} ya está en estado {fase.get('estado')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
