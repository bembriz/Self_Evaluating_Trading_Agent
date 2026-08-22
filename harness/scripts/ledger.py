#!/usr/bin/env python3
"""Módulo compartido: carga, validación y mutación del ledger de progreso.

Única fuente de verdad del % de avance del proyecto. Toda mutación pasa por
las funciones de este módulo; el agente nunca edita progress.yaml a mano.
"""

from __future__ import annotations

import datetime as dt
import statistics
from pathlib import Path

import yaml

PHASE_STATES = ("pending", "in_progress", "gate_requested", "done")
DELIVERABLE_STATES = ("pending", "done", "blocked")
GATE_STATES = ("pending", "requested", "approved", "rejected")
EXPECTED_PHASES = tuple(f"{i:02d}" for i in range(19))
DEFAULT_CAP_SIN_GATE = 0.90
ETA_BAND_DEFAULT = 0.30
ETA_BAND_MIN = 0.10
ETA_BAND_MAX = 0.50
ETA_BAND_MIN_DIAS = 5


class LedgerError(Exception):
    """Violación de esquema o de regla de negocio del ledger."""


def find_repo_root(start: Path | None = None) -> Path:
    current = Path(start).resolve() if start is not None else Path(__file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    raise LedgerError("No se encontró la raíz del repositorio (ni .git ni AGENTS.md)")


def default_ledger_path(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    return root / "harness" / "state" / "progress.yaml"


def load_ledger(path: Path | str | None = None) -> dict:
    ledger_path = Path(path) if path else default_ledger_path()
    if not ledger_path.exists():
        raise LedgerError(f"No existe el ledger en {ledger_path}")
    with ledger_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise LedgerError("El ledger no contiene un mapping YAML válido")
    return data


def save_ledger(data: dict, path: Path | str | None = None) -> None:
    ledger_path = Path(path) if path else default_ledger_path()
    data.setdefault("meta", {})["actualizado"] = dt.date.today().isoformat()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def validate(data: dict) -> list[str]:
    errores: list[str] = []
    meta = data.get("meta")
    if not isinstance(meta, dict) or "proyecto" not in meta:
        errores.append("meta.proyecto es obligatorio")
    reglas = (meta or {}).get("reglas", {})
    cap = float(reglas.get("cap_fase_sin_gate", DEFAULT_CAP_SIN_GATE))
    if not 0 < cap <= 1.0:
        errores.append(f"meta.reglas.cap_fase_sin_gate fuera de (0,1]: {cap}")
    phases = data.get("phases")
    if not isinstance(phases, dict) or not phases:
        return errores + ["phases debe ser un mapping con al menos una fase"]
    faltantes = [p for p in EXPECTED_PHASES if p not in phases]
    if faltantes:
        errores.append(f"Fases ausentes del PRD §79: {', '.join(faltantes)}")
    for pid, fase in sorted(phases.items()):
        prefijo = f"fases[{pid}]"
        if not isinstance(fase, dict):
            errores.append(f"{prefijo}: debe ser un mapping")
            continue
        if not fase.get("titulo"):
            errores.append(f"{prefijo}.titulo es obligatorio")
        estado = fase.get("estado", "pending")
        if estado not in PHASE_STATES:
            errores.append(f"{prefijo}.estado inválido: {estado!r}")
        entregables = fase.get("entregables", [])
        if not isinstance(entregables, list) or not entregables:
            errores.append(f"{prefijo}.entregables debe ser lista no vacía")
            continue
        vistos: set[str] = set()
        for i, ent in enumerate(entregables):
            sub = f"{prefijo}.entregables[{i}]"
            if not isinstance(ent, dict) or not ent.get("id"):
                errores.append(f"{sub}: falta 'id'")
                continue
            eid = ent["id"]
            if eid in vistos:
                errores.append(f"{sub}: id duplicado {eid!r}")
            vistos.add(eid)
            if ent.get("estado", "pending") not in DELIVERABLE_STATES:
                errores.append(f"{sub}({eid}).estado inválido")
            if ent.get("estado") == "done" and not ent.get("evidencia"):
                errores.append(f"{sub}({eid}): 'done' exige evidencia no vacía")
        gate = fase.get("gate_fase", {})
        if not isinstance(gate, dict) or gate.get("estado", "pending") not in GATE_STATES:
            errores.append(f"{prefijo}.gate_fase.estado inválido")
        if gate.get("estado") == "approved":
            pendientes = [e.get("id") for e in entregables if e.get("estado") != "done"]
            if pendientes:
                errores.append(f"{prefijo}: gate aprobado con entregables pendientes: {pendientes}")
    if data.get("blockers") is not None and not isinstance(data.get("blockers"), list):
        errores.append("blockers debe ser una lista")
    return errores


def require_valid(data: dict) -> None:
    errores = validate(data)
    if errores:
        detalle = "\n  - ".join(errores)
        raise LedgerError(f"Ledger inválido:\n  - {detalle}")


def get_phase(data: dict, phase_id: str) -> dict:
    fase = data.get("phases", {}).get(phase_id)
    if fase is None:
        raise LedgerError(f"Fase desconocida: {phase_id!r}")
    return fase


def find_deliverable(fase: dict, deliverable_id: str) -> dict:
    for ent in fase.get("entregables", []):
        if ent.get("id") == deliverable_id:
            return ent
    raise LedgerError(f"Entregable desconocido: {deliverable_id!r}")


def append_event(data: dict, fase_id: str, evento: str, detalle: str = "") -> None:
    data.setdefault("time_log", []).append(
        {
            "fecha": dt.date.today().isoformat(),
            "fase": fase_id,
            "evento": evento,
            "detalle": detalle,
        }
    )


def mark_deliverable(
    data: dict,
    phase_id: str,
    deliverable_id: str,
    evidencia: list[str],
) -> bool:
    require_valid(data)
    if not evidencia:
        raise LedgerError("mark_deliverable exige al menos una ruta de evidencia")
    fase = get_phase(data, phase_id)
    ent = find_deliverable(fase, deliverable_id)
    ya_done = ent.get("estado") == "done"
    ent["estado"] = "done"
    rutas = sorted(set(evidencia))
    previas = list(ent.get("evidencia") or [])
    ent["evidencia"] = sorted(set(previas) | set(rutas))
    if not ya_done:
        append_event(data, phase_id, "done", deliverable_id)
        return True
    return False


def block_deliverable(data: dict, phase_id: str, deliverable_id: str, motivo: str) -> None:
    require_valid(data)
    if not motivo.strip():
        raise LedgerError("Bloquear un entregable exige un motivo")
    fase = get_phase(data, phase_id)
    ent = find_deliverable(fase, deliverable_id)
    ent["estado"] = "blocked"
    ent["motivo_bloqueo"] = motivo.strip()
    append_event(data, phase_id, "blocked", f"{deliverable_id}: {motivo.strip()}")


def unblock_deliverable(data: dict, phase_id: str, deliverable_id: str) -> None:
    require_valid(data)
    fase = get_phase(data, phase_id)
    ent = find_deliverable(fase, deliverable_id)
    ent["estado"] = "pending"
    ent.pop("motivo_bloqueo", None)
    append_event(data, phase_id, "unblocked", deliverable_id)


def set_phase_status(data: dict, phase_id: str, estado: str) -> None:
    require_valid(data)
    if estado not in PHASE_STATES:
        raise LedgerError(f"Estado de fase inválido: {estado!r}")
    fase = get_phase(data, phase_id)
    anterior = fase.get("estado", "pending")
    fase["estado"] = estado
    if estado == "in_progress" and not fase.get("iniciada"):
        fase["iniciada"] = dt.date.today().isoformat()
    if estado == "done":
        fase["cerrada"] = dt.date.today().isoformat()
    if anterior != estado:
        append_event(data, phase_id, "phase_status", f"{anterior}→{estado}")


def request_gate(data: dict, phase_id: str) -> None:
    require_valid(data)
    fase = get_phase(data, phase_id)
    pendientes = [e["id"] for e in fase["entregables"] if e["estado"] != "done"]
    if pendientes:
        raise LedgerError(
            f"No se puede solicitar gate de {phase_id}: entregables sin terminar {pendientes}"
        )
    fase.setdefault("gate_fase", {})["estado"] = "requested"
    fase["gate_fase"]["solicitado"] = dt.date.today().isoformat()
    append_event(data, phase_id, "gate_requested")


def resolve_gate(data: dict, phase_id: str, approved: bool, comentario: str = "") -> None:
    require_valid(data)
    fase = get_phase(data, phase_id)
    if not approved:
        fase.setdefault("gate_fase", {})["estado"] = "rejected"
        append_event(data, phase_id, "gate_rejected", comentario)
        return
    pendientes = [e["id"] for e in fase["entregables"] if e["estado"] != "done"]
    if pendientes:
        raise LedgerError(
            f"Gate de {phase_id} rechazado automáticamente: quedan pendientes {pendientes}"
        )
    fase.setdefault("gate_fase", {})["estado"] = "approved"
    fase["gate_fase"]["resuelto"] = dt.date.today().isoformat()
    fase["gate_fase"]["comentario"] = comentario
    fase["estado"] = "done"
    fase["cerrada"] = dt.date.today().isoformat()
    append_event(data, phase_id, "gate_approved", comentario)


def add_blocker(data: dict, descripcion: str, fase: str = "") -> None:
    if not descripcion.strip():
        raise LedgerError("Un bloqueo exige descripción")
    data.setdefault("blockers", []).append(
        {"descripcion": descripcion.strip(), "fase": fase, "abierto": dt.date.today().isoformat()}
    )


def remove_blocker(data: dict, indice: int) -> None:
    blockers = data.setdefault("blockers", [])
    if indice < 0 or indice >= len(blockers):
        raise LedgerError(f"Índice de bloqueo inexistente: {indice}")
    blockers.pop(indice)


def compute_stats(data: dict) -> dict:
    require_valid(data)
    cap = float(
        data.get("meta", {}).get("reglas", {}).get("cap_fase_sin_gate", DEFAULT_CAP_SIN_GATE)
    )
    por_fase: dict[str, dict] = {}
    for pid, fase in sorted(data["phases"].items()):
        ents = fase["entregables"]
        total = len(ents)
        done = sum(1 for e in ents if e["estado"] == "done")
        blocked = sum(1 for e in ents if e["estado"] == "blocked")
        pendiente = total - done - blocked
        base = (done / total * 100.0) if total else 100.0
        gate_estado = fase.get("gate_fase", {}).get("estado", "pending")
        pct = base if gate_estado == "approved" else min(base, cap * 100.0)
        por_fase[pid] = {
            "titulo": fase.get("titulo", ""),
            "estado": fase.get("estado", "pending"),
            "total": total,
            "done": done,
            "blocked": blocked,
            "pendiente": pendiente,
            "pct": round(pct, 2),
            "base_pct": round(base, 2),
            "gate": gate_estado,
        }
    global_pct = round(sum(f["pct"] for f in por_fase.values()) / len(por_fase), 2)
    totales = {
        "entregables_total": sum(f["total"] for f in por_fase.values()),
        "done": sum(f["done"] for f in por_fase.values()),
        "blocked": sum(f["blocked"] for f in por_fase.values()),
        "pendiente": sum(f["pendiente"] for f in por_fase.values()),
        "fases_done": sum(1 for f in por_fase.values() if f["gate"] == "approved"),
    }
    return {"por_fase": por_fase, "global_pct": global_pct, "totales": totales}


def compute_eta(data: dict, stats: dict | None = None) -> dict | None:
    stats = stats or compute_stats(data)
    restante = stats["totales"]["pendiente"] + stats["totales"]["blocked"]
    eventos_done = [e for e in data.get("time_log", []) if e.get("evento") == "done"]
    unidades = len(eventos_done)
    if unidades == 0 or restante == 0:
        dias = 0.0 if restante == 0 else None
        if dias == 0.0:
            return {
                "velocity_per_day": None,
                "remaining": 0,
                "eta_days": 0.0,
                "banda": 0.0,
                "eta_rango_dias": (0, 0),
            }
        return None
    fechas = sorted({e["fecha"] for e in eventos_done})
    dias_distintos = len(fechas)
    velocidad = unidades / dias_distintos
    eta_dias = restante / velocidad
    banda = ETA_BAND_DEFAULT
    if dias_distintos >= ETA_BAND_MIN_DIAS:
        por_dia = [sum(1 for e in eventos_done if e["fecha"] == f) for f in fechas]
        media = statistics.fmean(por_dia)
        desv = statistics.pstdev(por_dia)
        cv = (desv / media) if media > 0 else ETA_BAND_MAX
        banda = max(ETA_BAND_MIN, min(ETA_BAND_MAX, cv))
    hoy = dt.date.today()
    bajo = max(0, round(eta_dias * (1 - banda)))
    alto = round(eta_dias * (1 + banda))
    return {
        "velocity_per_day": round(velocidad, 2),
        "remaining": restante,
        "eta_days": round(eta_dias, 1),
        "banda": round(banda, 2),
        "eta_rango_dias": (bajo, alto),
        "eta_fecha_rango": (
            (hoy + dt.timedelta(days=bajo)).isoformat(),
            (hoy + dt.timedelta(days=alto)).isoformat(),
        ),
    }


def markdown_summary(data: dict) -> str:
    stats = compute_stats(data)
    eta = compute_eta(data, stats)
    lineas: list[str] = []
    lineas.append("# Progreso del proyecto")
    lineas.append("")
    lineas.append(f"**Avance global: {stats['global_pct']}%** (calculado sobre evidencias)")
    lineas.append("")
    lineas.append("| Fase | Título | Estado | Done | Pend | Bloq | % | Gate |")
    lineas.append("|---|---|---|---|---|---|---|---|")
    for pid, f in stats["por_fase"].items():
        lineas.append(
            f"| {pid} | {f['titulo'][:38]} | {f['estado']} | {f['done']}/{f['total']} "
            f"| {f['pendiente']} | {f['blocked']} | {f['pct']}% | {f['gate']} |"
        )
    lineas.append("")
    t = stats["totales"]
    lineas.append(
        f"**Totales:** {t['done']} done · {t['pendiente']} pendiente · "
        f"{t['blocked']} bloqueados · {t['fases_done']}/19 fases con gate aprobado"
    )
    lineas.append("")
    if eta is None:
        lineas.append("**ETA:** sin datos suficientes aún (se requiere ≥1 entregable completado)")
    else:
        bajo, alto = eta["eta_rango_dias"]
        fechas = eta.get("eta_fecha_rango", ("-", "-"))
        lineas.append(
            f"**ETA:** {bajo}–{alto} días "
            f"(velocidad {eta['velocity_per_day']} entregables/día, "
            f"banda ±{int(eta['banda'] * 100)}%) → {fechas[0]} … {fechas[1]}"
        )
    lineas.append("")
    blockers = data.get("blockers") or []
    if blockers:
        lineas.append("## Bloqueos abiertos")
        for i, b in enumerate(blockers):
            lineas.append(
                f"- [{i}] ({b.get('fase', '—')}) {b['descripcion']} (desde {b['abierto']})"
            )
    else:
        lineas.append("**Bloqueos:** ninguno")
    return "\n".join(lineas) + "\n"
