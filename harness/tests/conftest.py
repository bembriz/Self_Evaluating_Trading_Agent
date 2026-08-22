import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ledger as ld
import pytest


def make_entregable(eid: str, estado: str = "pending", evidencia: list | None = None) -> dict:
    return {
        "id": eid,
        "descripcion": f"entregable {eid}",
        "estado": estado,
        "evidencia": evidencia if evidencia is not None else [],
    }


def make_fase(pid: str, n: int = 2) -> dict:
    return {
        "titulo": f"Fase {pid}",
        "estado": "pending",
        "iniciada": None,
        "cerrada": None,
        "entregables": [make_entregable(f"d{pid}_{j}") for j in range(n)],
        "gate_fase": {"estado": "pending", "solicitado": None, "resuelto": None},
    }


def make_ledger(n_ents_fase0: int = 3, cap: float = 0.90) -> dict:
    return {
        "meta": {"proyecto": "test", "reglas": {"cap_fase_sin_gate": cap}},
        "phases": {
            f"{i:02d}": make_fase(f"{i:02d}", n_ents_fase0 if i == 0 else 1) for i in range(19)
        },
        "time_log": [],
        "blockers": [],
    }


@pytest.fixture
def ledger(tmp_path):
    ruta = tmp_path / "progress.yaml"
    data = make_ledger()
    ld.save_ledger(data, ruta)
    return ruta
