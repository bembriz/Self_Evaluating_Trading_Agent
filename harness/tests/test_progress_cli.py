import ledger as ld
from progress import main


def argv_mark_done(ledger: object) -> list[str]:
    return [
        "mark-done",
        "--phase",
        "03",
        "--deliverable",
        "d03_0",
        "--evidence",
        "docs/phases/03/evidence/x.log",
        "--ledger",
        str(ledger),
    ]


def test_report_imprime_tabla(ledger, capsys):
    rc = main(["report", "--ledger", str(ledger)])
    salida = capsys.readouterr().out
    assert rc == 0
    assert "Avance global" in salida
    assert "| 00 |" in salida


def test_mark_done_via_cli(ledger, capsys):
    rc = main(argv_mark_done(ledger))
    assert rc == 0
    data = ld.load_ledger(ledger)
    ent = ld.find_deliverable(data["phases"]["03"], "d03_0")
    assert ent["estado"] == "done"
    assert "registrado" in capsys.readouterr().out


def test_block_y_unblock_via_cli(ledger):
    argv_block = [
        "block",
        "--phase",
        "04",
        "--deliverable",
        "d04_0",
        "--motivo",
        "esperando ws",
        "--ledger",
        str(ledger),
    ]
    assert main(argv_block) == 0

    data = ld.load_ledger(ledger)
    entregable = ld.find_deliverable(data["phases"]["04"], "d04_0")
    assert entregable["estado"] == "blocked"

    argv_unblock = [
        "unblock",
        "--phase",
        "04",
        "--deliverable",
        "d04_0",
        "--ledger",
        str(ledger),
    ]
    assert main(argv_unblock) == 0


def test_fase_status_gate_flow(ledger, capsys):
    argv_status = [
        "phase-status",
        "--phase",
        "01",
        "--estado",
        "in_progress",
        "--ledger",
        str(ledger),
    ]
    assert main(argv_status) == 0

    for eid in ("d00_0", "d00_1", "d00_2"):
        argv_done = [
            "mark-done",
            "--phase",
            "00",
            "--deliverable",
            eid,
            "--evidence",
            "e.log",
            "--ledger",
            str(ledger),
        ]
        main(argv_done)

    assert main(["gate-request", "--phase", "00", "--ledger", str(ledger)]) == 0

    argv_reject = [
        "gate-reject",
        "--phase",
        "00",
        "--comentario",
        "falta UAT",
        "--ledger",
        str(ledger),
    ]
    assert main(argv_reject) == 0

    argv_approve = [
        "gate-approve",
        "--phase",
        "00",
        "--comentario",
        "OK",
        "--ledger",
        str(ledger),
    ]
    rc = main(argv_approve)
    assert rc == 0

    data = ld.load_ledger(ledger)
    fase = data["phases"]["00"]
    assert fase["estado"] == "done"
    assert fase["gate_fase"]["estado"] == "approved"
    assert "GATE APROBADO" in capsys.readouterr().out


def test_blockers_add_remove_via_cli(ledger):
    argv_add = [
        "blocker-add",
        "--texto",
        "sin API key",
        "--phase",
        "12",
        "--ledger",
        str(ledger),
    ]
    assert main(argv_add) == 0

    argv_rm = ["blocker-rm", "--index", "0", "--ledger", str(ledger)]
    assert main(argv_rm) == 0


def test_add_phase_via_cli(ledger, capsys):
    rc = main(
        [
            "add-phase",
            "--phase",
            "16b",
            "--titulo",
            "Fase correctiva 16b",
            "--deliverable",
            "fix-atr=runner calcula ATR",
            "--deliverable",
            "fix-ws=close tolerante",
            "--ledger",
            str(ledger),
        ]
    )
    assert rc == 0
    assert "fase 16b registrada (2 entregables)" in capsys.readouterr().out
    data = ld.load_ledger(ledger)
    fase = ld.get_phase(data, "16b")
    assert [e["id"] for e in fase["entregables"]] == ["fix-atr", "fix-ws"]
    assert fase["entregables"][0]["descripcion"] == "runner calcula ATR"


def test_add_phase_cli_rechaza_deliverable_sin_formato(ledger):
    import pytest

    with pytest.raises(SystemExit):
        main(
            [
                "add-phase",
                "--phase",
                "16b",
                "--titulo",
                "t",
                "--deliverable",
                "sin-separador",
                "--ledger",
                str(ledger),
            ]
        )
