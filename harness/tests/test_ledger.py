import ledger as ld
import pytest
from conftest import make_ledger


def test_find_repo_root_encuentra_raiz():
    raiz = ld.find_repo_root()
    assert (raiz / "harness" / "scripts" / "ledger.py").exists()


def test_load_ledger_inexistente(tmp_path):
    with pytest.raises(ld.LedgerError):
        ld.load_ledger(tmp_path / "no.yaml")


def test_validate_ok(ledger):
    assert ld.validate(ld.load_ledger(ledger)) == []


@pytest.mark.parametrize(
    "mutador,fragmento",
    [
        (lambda d: d["phases"].pop("05"), "ausentes"),
        (lambda d: d["phases"]["00"].__setitem__("estado", "raro"), "estado inv"),
        (
            lambda d: d["phases"]["00"]["entregables"][0].__setitem__("estado", "done"),
            "exige evidencia",
        ),
        (
            lambda d: d["phases"]["00"]["entregables"][1].__setitem__(
                "id", d["phases"]["00"]["entregables"][0]["id"]
            ),
            "duplicado",
        ),
        (lambda d: d["meta"].__setitem__("reglas", {"cap_fase_sin_gate": 1.5}), "cap_fase"),
        (lambda d: d["phases"]["00"].pop("entregables"), "entregables"),
        (lambda d: d.__setitem__("blockers", "x"), "blockers"),
    ],
)
def test_validate_detecta_errores(ledger, mutador, fragmento):
    data = ld.load_ledger(ledger)
    mutador(data)
    errores = ld.validate(data)
    assert any(fragmento in e for e in errores)


def test_validate_gate_aprobado_con_pendientes(ledger):
    data = ld.load_ledger(ledger)
    data["phases"]["00"]["gate_fase"]["estado"] = "approved"
    errores = ld.validate(data)
    assert any("gate aprobado con entregables pendientes" in e for e in errores)


def test_require_valid_lanza(ledger):
    data = ld.load_ledger(ledger)
    data["phases"].pop("07")
    with pytest.raises(ld.LedgerError):
        ld.require_valid(data)


def test_get_phase_desconocida(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.get_phase(data, "99")


def test_mark_deliverable_exige_evidencia(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.mark_deliverable(data, "00", "d00_0", [])


def test_mark_deliverable_registra_y_es_idempotente(ledger):
    data = ld.load_ledger(ledger)
    cambio1 = ld.mark_deliverable(data, "00", "d00_0", ["docs/a.md"])
    assert cambio1 is True
    ent = ld.find_deliverable(ld.get_phase(data, "00"), "d00_0")
    assert ent["estado"] == "done"
    assert ent["evidencia"] == ["docs/a.md"]
    assert len(data["time_log"]) == 1
    cambio2 = ld.mark_deliverable(data, "00", "d00_0", ["docs/b.md"])
    assert cambio2 is False
    ent = ld.find_deliverable(ld.get_phase(data, "00"), "d00_0")
    assert ent["evidencia"] == ["docs/a.md", "docs/b.md"]
    assert len(data["time_log"]) == 1


def test_block_y_unblock(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.block_deliverable(data, "00", "d00_1", "   ")
    ld.block_deliverable(data, "00", "d00_1", "esperando API key")
    fase = ld.get_phase(data, "00")
    ent = ld.find_deliverable(fase, "d00_1")
    assert ent["estado"] == "blocked"
    assert ent["motivo_bloqueo"] == "esperando API key"
    ld.unblock_deliverable(data, "00", "d00_1")
    assert ent["estado"] == "pending"
    assert "motivo_bloqueo" not in ent


def test_set_phase_status(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.set_phase_status(data, "01", "volando")
    ld.set_phase_status(data, "01", "in_progress")
    assert data["phases"]["01"]["iniciada"] is not None
    primera = data["phases"]["01"]["iniciada"]
    ld.set_phase_status(data, "01", "pending")
    ld.set_phase_status(data, "01", "in_progress")
    assert data["phases"]["01"]["iniciada"] == primera


def test_request_gate_exige_todo_done(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.request_gate(data, "00")
    for eid in ("d00_0", "d00_1", "d00_2"):
        ld.mark_deliverable(data, "00", eid, [f"ev/{eid}.txt"])
    ld.request_gate(data, "00")
    assert data["phases"]["00"]["gate_fase"]["estado"] == "requested"


def test_resolve_gate_approve_exige_todo_done(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.resolve_gate(data, "00", True)


def test_resolve_gate_reject_y_approve(ledger):
    data = ld.load_ledger(ledger)
    for eid in ("d00_0", "d00_1", "d00_2"):
        ld.mark_deliverable(data, "00", eid, [f"ev/{eid}.txt"])
    ld.resolve_gate(data, "00", False, "falta UAT")
    assert data["phases"]["00"]["gate_fase"]["estado"] == "rejected"
    ld.resolve_gate(data, "00", True, "OK usuario")
    fase = data["phases"]["00"]
    assert fase["gate_fase"]["estado"] == "approved"
    assert fase["estado"] == "done"
    assert fase["cerrada"] is not None


def test_blockers_add_remove(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError):
        ld.add_blocker(data, "")
    ld.add_blocker(data, "sin credenciales testnet", "12")
    with pytest.raises(ld.LedgerError):
        ld.remove_blocker(data, 5)
    ld.remove_blocker(data, 0)
    assert data["blockers"] == []


def test_stats_cap_sin_gate():
    data = make_ledger(n_ents_fase0=2)
    ld.mark_deliverable(data, "00", "d00_0", ["a.txt"])
    stats = ld.compute_stats(data)
    f0 = stats["por_fase"]["00"]
    assert f0["base_pct"] == 50.0
    assert f0["pct"] == 50.0
    for eid in ("d00_0", "d00_1"):
        estado = ld.find_deliverable(data["phases"]["00"], eid)["estado"]
        if estado != "done":
            ld.mark_deliverable(data, "00", eid, ["b.txt"])
    stats = ld.compute_stats(data)
    assert stats["por_fase"]["00"]["base_pct"] == 100.0
    assert stats["por_fase"]["00"]["pct"] == 90.0


def test_stats_gate_aprobado_da_100():
    data = make_ledger(n_ents_fase0=2)
    for eid in ("d00_0", "d00_1"):
        ld.mark_deliverable(data, "00", eid, ["e.txt"])
    data["phases"]["00"]["gate_fase"]["estado"] = "approved"
    f0 = ld.compute_stats(data)["por_fase"]["00"]
    assert f0["pct"] == 100.0
    assert f0["pendiente"] == 0 and f0["blocked"] == 0


def test_global_pct_es_media_de_fases():
    data = make_ledger()
    stats = ld.compute_stats(data)
    assert stats["global_pct"] == 0.0
    ld.mark_deliverable(data, "05", list(data["phases"]["05"]["entregables"])[0]["id"], ["x.txt"])
    data["phases"]["05"]["gate_fase"]["estado"] = "approved"
    stats = ld.compute_stats(data)
    esperado = round(stats["por_fase"]["05"]["pct"] / 19, 2)
    assert stats["global_pct"] == esperado


def test_eta_sin_eventos_devuelve_none():
    data = make_ledger()
    assert ld.compute_eta(data) is None


def test_eta_proyecto_terminado():
    data = make_ledger()
    for fase in data["phases"].values():
        for ent in fase["entregables"]:
            ent["estado"] = "done"
            ent["evidencia"] = ["e"]
    eta = ld.compute_eta(data)
    assert eta is not None and eta["eta_days"] == 0.0


def test_eta_velocidad_un_dia_banda_default():
    data = make_ledger()
    ids = [e["id"] for e in data["phases"]["00"]["entregables"]]
    for eid in ids[:3]:
        ld.mark_deliverable(data, "00", eid, ["e"])
    eta = ld.compute_eta(data)
    restante = sum(
        len([e for e in f["entregables"] if e["estado"] != "done"]) for f in data["phases"].values()
    )
    assert eta["remaining"] == restante
    assert eta["velocity_per_day"] == 3.0
    assert abs(eta["eta_days"] - restante / 3) < 0.1
    assert eta["banda"] == 0.30
    bajo, alto = eta["eta_rango_dias"]
    assert bajo < alto


def test_eta_banda_por_varianza_tras_cinco_dias():
    data = make_ledger()
    eventos = []
    dias = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05"]
    for dia, n in zip(dias, [10, 10, 10, 10, 1], strict=True):
        for j in range(n):
            eventos.append({"fecha": dia, "fase": "00", "evento": "done", "detalle": f"x{j}"})
    data["time_log"] = eventos
    eta = ld.compute_eta(data)
    assert eta["banda"] >= ld.ETA_BAND_MIN and eta["banda"] <= ld.ETA_BAND_MAX
    assert eta["velocity_per_day"] == 8.2


def test_markdown_summary_contiene_lo_esencial(ledger):
    data = ld.load_ledger(ledger)
    texto = ld.markdown_summary(data)
    assert "Avance global" in texto
    assert "| Fase | Título" in texto
    assert "ETA:" in texto
    assert "ninguno" in texto.lower()


def test_save_actualiza_meta(ledger):
    data = ld.load_ledger(ledger)
    data["meta"].pop("actualizado", None)
    ld.save_ledger(data, ledger)
    data = ld.load_ledger(ledger)
    assert data["meta"]["actualizado"] is not None


def test_add_phase_registra_fase_correctiva(ledger):
    data = ld.load_ledger(ledger)
    ld.add_phase(
        data,
        "16b",
        "Fase correctiva: fix ATR paper-runner",
        [("fix-atr", "runner calcula ATR"), ("fix-ws", "close tolerante")],
    )
    fase = ld.get_phase(data, "16b")
    assert fase["titulo"] == "Fase correctiva: fix ATR paper-runner"
    assert fase["estado"] == "pending"
    assert [e["id"] for e in fase["entregables"]] == ["fix-atr", "fix-ws"]
    assert all(e["estado"] == "pending" for e in fase["entregables"])
    assert fase["gate_fase"]["estado"] == "pending"
    assert ld.validate(data) == []
    assert data["time_log"][-1]["evento"] == "phase_added"


def test_add_phase_rechaza_duplicados_y_vacios(ledger):
    data = ld.load_ledger(ledger)
    with pytest.raises(ld.LedgerError, match="ya existe"):
        ld.add_phase(data, "00", "otra", [("x", "y")])
    with pytest.raises(ld.LedgerError, match="título"):
        ld.add_phase(data, "16b", "  ", [("x", "y")])
    with pytest.raises(ld.LedgerError, match="al menos un entregable"):
        ld.add_phase(data, "16b", "t", [])
    with pytest.raises(ld.LedgerError, match="duplicados"):
        ld.add_phase(data, "16b", "t", [("x", "a"), ("x", "b")])
    with pytest.raises(ld.LedgerError, match="vacíos"):
        ld.add_phase(data, "16b", "t", [(" ", "a")])
    with pytest.raises(ld.LedgerError, match="id de fase"):
        ld.add_phase(data, " ", "t", [("x", "a")])
