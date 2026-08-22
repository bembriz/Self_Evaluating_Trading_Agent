#!/usr/bin/env python3
"""CLI de progreso: reporte objetivo y únicas mutaciones permitidas del ledger.

Uso:
  progress.py report [--ledger RUTA]
  progress.py mark-done --phase 00 --deliverable agents-md --evidence AGENTS.md [--evidence OTRA]
  progress.py block --phase 00 --deliverable X --motivo "..."
  progress.py unblock --phase 00 --deliverable X
  progress.py phase-status --phase 01 --estado in_progress
  progress.py gate-request --phase 00
  progress.py gate-approve --phase 00 --comentario "OK"
  progress.py gate-reject --phase 00 --comentario "falta UAT"
  progress.py blocker-add --texto "..." [--phase 03]
  progress.py blocker-rm --index 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ledger as ld


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="progress", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ledger", default=None)

    sub.add_parser("report", parents=[common], help="Resumen Markdown del progreso")
    m = sub.add_parser("mark-done", parents=[common])
    m.add_argument("--phase", required=True)
    m.add_argument("--deliverable", required=True)
    m.add_argument("--evidence", action="append", required=True)
    b = sub.add_parser("block", parents=[common])
    b.add_argument("--phase", required=True)
    b.add_argument("--deliverable", required=True)
    b.add_argument("--motivo", required=True)
    u = sub.add_parser("unblock", parents=[common])
    u.add_argument("--phase", required=True)
    u.add_argument("--deliverable", required=True)
    ps = sub.add_parser("phase-status", parents=[common])
    ps.add_argument("--phase", required=True)
    ps.add_argument("--estado", choices=ld.PHASE_STATES, required=True)
    gr = sub.add_parser("gate-request", parents=[common])
    gr.add_argument("--phase", required=True)
    ga = sub.add_parser("gate-approve", parents=[common])
    ga.add_argument("--phase", required=True)
    ga.add_argument("--comentario", default="")
    gx = sub.add_parser("gate-reject", parents=[common])
    gx.add_argument("--phase", required=True)
    gx.add_argument("--comentario", default="")
    ba = sub.add_parser("blocker-add", parents=[common])
    ba.add_argument("--texto", required=True)
    ba.add_argument("--phase", default="")
    br = sub.add_parser("blocker-rm", parents=[common])
    br.add_argument("--index", type=int, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data = ld.load_ledger(args.ledger)
    if args.cmd == "report":
        print(ld.markdown_summary(data))
        return 0
    if args.cmd == "mark-done":
        changed = ld.mark_deliverable(data, args.phase, args.deliverable, args.evidence)
        print(f"{'registrado' if changed else 'ya estaba done'}: {args.phase}/{args.deliverable}")
    elif args.cmd == "block":
        ld.block_deliverable(data, args.phase, args.deliverable, args.motivo)
        print(f"bloqueado: {args.phase}/{args.deliverable}")
    elif args.cmd == "unblock":
        ld.unblock_deliverable(data, args.phase, args.deliverable)
        print(f"desbloqueado: {args.phase}/{args.deliverable}")
    elif args.cmd == "phase-status":
        ld.set_phase_status(data, args.phase, args.estado)
        print(f"fase {args.phase} → {args.estado}")
    elif args.cmd == "gate-request":
        ld.request_gate(data, args.phase)
        print(f"gate solicitado para fase {args.phase}: requiere aprobación humana")
    elif args.cmd == "gate-approve":
        ld.resolve_gate(data, args.phase, True, args.comentario)
        print(f"GATE APROBADO por usuario: fase {args.phase}")
    elif args.cmd == "gate-reject":
        ld.resolve_gate(data, args.phase, False, args.comentario)
        print(f"gate rechazado: fase {args.phase}")
    elif args.cmd == "blocker-add":
        ld.add_blocker(data, args.texto, args.phase)
        print("bloqueo registrado")
    elif args.cmd == "blocker-rm":
        ld.remove_blocker(data, args.index)
        print("bloqueo eliminado")
    ld.save_ledger(data, args.ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
