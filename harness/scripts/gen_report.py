#!/usr/bin/env python3
"""Genera el esqueleto del reporte de fase (PRD §75-76) con datos verificados prellenados.

Uso: gen_report.py --phase 00 [--out docs/phases/phase-00-report.md]
Solo sustituye placeholders con datos objetivos del ledger; las secciones
cualitativas quedan marcadas para completar antes de solicitar el gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger as ld

REPO = ld.find_repo_root()
TEMPLATE = REPO / "harness" / "templates" / "reporte-fase.md"  # noqa: E501


def entregables_tabla(fase: dict) -> str:
    lineas = ["| Entregable | Descripción | Estado | Evidencia |", "|---|---|---|---|"]
    for ent in fase["entregables"]:
        ev = "<br>".join(f"`{e}`" for e in ent.get("evidencia", [])) or "—"
        estado = (
            "✅ done"
            if ent["estado"] == "done"
            else ("⛔ blocked" if ent["estado"] == "blocked" else "⏳ pending")
        )
        lineas.append(f"| `{ent['id']}` | {ent.get('descripcion', '')} | {estado} | {ev} |")
    return "\n".join(lineas)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gen-report", description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    data = ld.load_ledger(args.ledger)
    fase = ld.get_phase(data, args.phase)
    stats = ld.compute_stats(data)["por_fase"][args.phase]
    plantilla = TEMPLATE.read_text(encoding="utf-8")

    sustituciones = {
        "{{FASE}}": args.phase,
        "{{TITULO}}": fase.get("titulo", ""),
        "{{FECHA}}": dt.date.today().isoformat(),
        "{{ESTADO_FASE}}": fase.get("estado", ""),
        "{{PCT_FASE}}": f"{stats['pct']}%",
        "{{PCT_GLOBAL}}": f"{ld.compute_stats(data)['global_pct']}%",
        "{{ENTREGABLES_TABLA}}": entregables_tabla(fase),
        "{{GATE_ESTADO}}": fase.get("gate_fase", {}).get("estado", "pending"),
    }
    contenido = plantilla
    for clave, valor in sustituciones.items():
        contenido = contenido.replace(clave, valor)

    destino = (
        Path(args.out) if args.out else REPO / "docs" / "phases" / f"phase-{args.phase}-report.md"
    )
    if destino.exists() and not args.force:
        print(f"AVISO: {destino.name} ya existe; usa --force para regenerar. No se sobrescribió.")
        return 1
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    print(f"Reporte generado: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
