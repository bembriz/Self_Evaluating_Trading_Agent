import subprocess
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / "scripts" / "evidence.sh"


def test_sintaxis_bash_valida():
    rc = subprocess.run(["bash", "-n", str(EVIDENCE)], capture_output=True)
    assert rc.returncode == 0


def ejecutar(tmp_path: Path, *args, cwd=None):
    return subprocess.run(
        ["bash", str(EVIDENCE), *args], cwd=cwd or tmp_path, capture_output=True, text=True
    )


def test_argumentos_invalidos(tmp_path):
    rc = ejecutar(tmp_path)
    assert rc.returncode == 64
    rc = ejecutar(tmp_path, "00", "x", "sin-separador", "true")
    assert rc.returncode == 64


def test_registra_evidencia_y_propaga_exit(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    log_dir = repo / "docs" / "phases" / "00" / "evidence"

    ok = ejecutar(repo, "00", "salida-ok", "--", "true")
    assert ok.returncode == 0
    assert "[evidence] salida-ok registrado" in ok.stdout

    fail = ejecutar(repo, "00", "comando-fail", "--", "false")
    assert fail.returncode == 1

    log_ok = (log_dir / "salida-ok.log").read_text(encoding="utf-8")
    assert "exit=0" in log_ok and "comando: true" in log_ok
    log_fail = (log_dir / "comando-fail.log").read_text(encoding="utf-8")
    assert "exit=1" in log_fail

    indice = (log_dir / "log.md").read_text(encoding="utf-8")
    assert "salida-ok" in indice and "comando-fail" in indice
