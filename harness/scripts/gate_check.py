#!/usr/bin/env python3
"""Validador objetivo de gates de fase (DoD del PRD §77).

Comprueba mecánicamente lo verificable y produce un checklist PASS/FAIL/MANUAL.
UAT y aprobación humana son siempre MANUAL: nunca los aprueba este script.

Uso:
  gate_check.py --phase 00 [--ledger RUTA] [--json]
  gate_check.py --phase 00 --record-approval   (solo tras aprobación explícita del usuario)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger as ld

COVERAGE_MINIMA_DEFAULT = 90.0


def check_evidence_exists(root: Path, ruta: str) -> bool:
    return (root / ruta).exists()


def read_coverage_pct(root: Path, phase_id: str) -> float | None:
    for candidata in (
        root / "docs" / "phases" / phase_id / "evidence" / "coverage.json",
        root / "coverage.json",
    ):
        if candidata.exists():
            try:
                datos = json.loads(candidata.read_text(encoding="utf-8"))
                return float(datos.get("totals", {}).get("percent_covered", -1))
            except (json.JSONDecodeError, ValueError, AttributeError):
                return None
    return None


def run_checks(root: Path, data: dict, phase_id: str) -> list[dict]:
    fase = ld.get_phase(data, phase_id)
    checks: list[dict] = []

    pendientes = [e["id"] for e in fase["entregables"] if e["estado"] != "done"]
    checks.append(
        {
            "id": "scope-complete",
            "descripcion": "Todos los entregables de la fase en estado done",
            "tipo": "auto",
            "estado": "PASS" if not pendientes else "FAIL",
            "detalle": (
                f"pendientes: {pendientes}"
                if pendientes
                else f"{len(fase['entregables'])} entregables verificados en ledger"
            ),
        }
    )

    sin_ruta = []
    for ent in fase["entregables"]:
        for ev in ent.get("evidencia", []):
            if not check_evidence_exists(root, ev):
                sin_ruta.append(f"{ent['id']}→{ev}")
    checks.append(
        {
            "id": "evidence-files",
            "descripcion": "Toda evidencia declarada existe en el repositorio",
            "tipo": "auto",
            "estado": "PASS" if not sin_ruta else "FAIL",
            "detalle": "; ".join(sin_ruta[:8]) if sin_ruta else "rutas verificadas",
        }
    )

    umbral = float(
        data.get("meta", {})
        .get("reglas", {})
        .get("coverage_minima_por_fase", {})
        .get(phase_id, COVERAGE_MINIMA_DEFAULT)
    )
    cov = read_coverage_pct(root, phase_id)
    if cov is None:
        estado_cov = "MANUAL"
        detalle_cov = (
            "sin coverage.json en evidence; si la fase no produce código, justificar en el reporte"
        )
    elif cov >= umbral:
        estado_cov = "PASS"
        detalle_cov = f"{cov:.2f}% ≥ {umbral}%"
    else:
        estado_cov = "FAIL"
        detalle_cov = f"{cov:.2f}% < {umbral}% exigido"
    checks.append(
        {
            "id": "coverage-gate",
            "descripcion": f"Cobertura mínima {umbral}% (PRD §70)",
            "tipo": "auto" if cov is not None else "manual",
            "estado": estado_cov,
            "detalle": detalle_cov,
        }
    )

    log_dir = root / "docs" / "phases" / phase_id / "evidence"
    for nombre_check, archivo in (("lint", "lint.log"), ("typing", "typing.log")):
        existe = (log_dir / archivo).exists()
        contenido = (log_dir / archivo).read_text(encoding="utf-8") if existe else ""
        ok = existe and "exit=0" in contenido
        checks.append(
            {
                "id": f"{nombre_check}-green",
                "descripcion": f"{nombre_check} ejecutado con éxito (PRD §77)",
                "tipo": "auto" if existe else "manual",
                "estado": "PASS" if ok else ("FAIL" if existe and not ok else "MANUAL"),
                "detalle": archivo if existe else "sin registro; usar harness/scripts/evidence.sh",
            }
        )

    uat_path = root / "docs" / "uat" / f"phase-{phase_id}-uat.md"
    uat_existe = uat_path.exists()
    uat_texto = uat_path.read_text(encoding="utf-8") if uat_existe else ""
    uat_visible = re.sub(r"<!--.*?-->", "", uat_texto, flags=re.S)
    uat_ok = uat_existe and "VEREDICTO UAT: APPROVED" in uat_visible
    checks.append(
        {
            "id": "uat-approved",
            "descripcion": "UAT ejecutado y aprobado por el usuario (HITL)",
            "tipo": "manual",
            "estado": "PASS" if uat_ok else "MANUAL",
            "detalle": str(uat_path.name) if uat_existe else "checklist aún no generado",
        }
    )

    gate_estado = fase.get("gate_fase", {}).get("estado", "pending")
    checks.append(
        {
            "id": "user-approval",
            "descripcion": "Aprobación humana registrada en ledger",
            "tipo": "manual",
            "estado": "PASS" if gate_estado == "approved" else "MANUAL",
            "detalle": f"gate_fase={gate_estado}",
        }
    )
    return checks


def summarize(checks: list[dict]) -> tuple[int, int, int]:
    pass_n = sum(1 for c in checks if c["estado"] == "PASS")
    fail_n = sum(1 for c in checks if c["estado"] == "FAIL")
    manual_n = sum(1 for c in checks if c["estado"] == "MANUAL")
    return pass_n, fail_n, manual_n


def render(checks: list[dict], phase_id: str, titulo: str) -> str:
    lineas = [
        f"# Gate check — Fase {phase_id}: {titulo}",
        "",
        "| Check | Tipo | Estado | Detalle |",
        "|---|---|---|---|",
    ]
    for c in checks:
        lineas.append(f"| {c['id']} | {c['tipo']} | **{c['estado']}** | {c['detalle']} |")
    p, f, m = summarize(checks)
    lineas += ["", f"**Resultado:** {p} PASS · {f} FAIL · {m} MANUAL"]
    if f == 0 and m == 0:
        lineas.append("**El gate puede solicitarse al usuario.**")
    elif f > 0:
        lineas.append("**BLOQUEADO: corrige los FAIL antes de solicitar el gate.**")
    else:
        lineas.append(
            "**Pendiente de acciones humanas (MANUAL): completa UAT/aprobación antes del gate.**"
        )
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gate-check", description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--record-approval",
        action="store_true",
        help="Registra la aprobación HUMANA (solo tras consentimiento explícito)",
    )
    args = parser.parse_args(argv)

    root = ld.find_repo_root(Path(args.ledger).resolve().parent if args.ledger else None)
    data = ld.load_ledger(args.ledger)
    fase = ld.get_phase(data, args.phase)
    checks = run_checks(root, data, args.phase)
    p, f, m = summarize(checks)

    if args.json:
        resumen = {"phase": args.phase, "checks": checks, "pass": p, "fail": f, "manual": m}
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
    else:
        print(render(checks, args.phase, fase.get("titulo", "")))

    if args.record_approval:
        if f > 0:
            print("ERROR: hay FAIL objetivos; no se registra aprobación.", file=sys.stderr)
            return 2
        if m > 0:
            print(
                "ERROR: quedan items MANUAL (UAT/usuario);",
                "obtén y registra su decisión primero.",
                file=sys.stderr,
            )
            return 3
        ld.resolve_gate(
            data, args.phase, True, comentario="Aprobado vía gate_check --record-approval"
        )
        ld.save_ledger(data, args.ledger)
        print(f"Aprobación registrada en ledger para fase {args.phase}.")
        return 0

    return 1 if f > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
