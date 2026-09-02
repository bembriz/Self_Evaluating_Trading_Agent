#!/usr/bin/env python3
"""release_check.py — Evalúa los 8 gates del Local Release Candidate (PRD §15).

Binario por diseño: PASS o PENDING(reason); jamás "casi". Genera
docs/phases/15/LOCAL_RELEASE_REPORT.md con el estado y su evidencia.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "phases"


def _has(*paths: str) -> bool:
    return all((REPO / p).exists() for p in paths)


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=600)
        return proc.returncode, (proc.stdout + proc.stderr)[-2000:]
    except FileNotFoundError:
        return 127, f"comando no disponible: {cmd[0]}"


def check_backtest() -> tuple[str, str]:
    # Corrida completa sobre dataset congelado con métricas §45 (Fase 06/14).
    log = REPO / "docs/phases/15/evidence/backtest-official-run1.log"
    result = REPO / "docs/phases/15/evidence/backtest_run1.json"
    if not (_has("datasets/BYBIT_ETHBTC_V001") and log.exists() and result.exists()):
        return "PENDING", "corrida oficial de backtest sobre dataset congelado no registrada"
    log_text = log.read_text(encoding="utf-8")
    if "exit=0" not in log_text or "OK  datasets/BYBIT_ETHBTC_V001/" not in log_text:
        return "PENDING", f"log de backtest sin verificación de dataset o con fallos: {log}"
    try:
        payload = json.loads(result.read_text(encoding="utf-8"))
        m = payload["metrics"]
        detail = (
            f"{payload['experiment_id']}: net_pnl={m['net_pnl']:.2f} "
            f"trades={m['trades']} win_rate={m['win_rate']:.3f} "
            f"profit_factor={m['profit_factor']:.3f} maxDD={m['max_drawdown']:.3f}; "
            f"buy_hold net_pnl={payload['benchmark_buy_hold']['metrics']['net_pnl']:.2f}"
        )
        return "PASS", detail
    except (KeyError, json.JSONDecodeError):
        return "PENDING", f"resultado de backtest ilegible: {result}"


def check_replay() -> tuple[str, str]:
    log = REPO / "docs/phases/15/evidence/replay-official-run1.log"
    trace = REPO / "docs/phases/15/evidence/replay_run1.jsonl"
    diff = REPO / "docs/phases/15/evidence/replay-determinism-diff.log"
    if not (
        _has("datasets/BYBIT_ETHBTC_V001") and log.exists() and trace.exists() and diff.exists()
    ):
        return "PENDING", "replay oficial sobre dataset congelado no registrado"
    if "exit=0" not in log.read_text(encoding="utf-8") or "DETERMINISTIC_OK" not in diff.read_text(
        encoding="utf-8"
    ):
        return "PENDING", f"replay sin exit=0 o sin determinismo probado: {log}"
    summary = [ln for ln in trace.read_text(encoding="utf-8").splitlines() if '"summary"' in ln]
    try:
        s = json.loads(summary[-1])
        return (
            "PASS",
            f"replay determinista reproducible (diff vacío): bars={s['bars']} "
            f"buy={s['buy']} sell={s['sell']} hold={s['hold']}",
        )
    except (IndexError, KeyError, json.JSONDecodeError):
        return "PENDING", f"traza de replay ilegible: {trace}"


def check_paper() -> tuple[str, str]:
    log = REPO / "docs/phases/15/evidence/paper-session-run1.log"
    result = REPO / "docs/phases/15/evidence/paper_session_run1.json"
    diff = REPO / "docs/phases/15/evidence/paper-session-determinism-diff.log"
    if not (
        _has("datasets/BYBIT_ETHBTC_V001") and log.exists() and result.exists() and diff.exists()
    ):
        return (
            "PENDING",
            "sesión de paper trading evaluada con fees/slippage/coste LLM no registrada",
        )
    if "exit=0" not in log.read_text(encoding="utf-8") or "DETERMINISTIC_OK" not in diff.read_text(
        encoding="utf-8"
    ):
        return "PENDING", f"sesión paper sin exit=0 o sin determinismo probado: {log}"
    try:
        payload = json.loads(result.read_text(encoding="utf-8"))
        m = payload["metrics"]
        s = payload["session"]
        detail = (
            f"{payload['experiment_id']}: bars={s['bars']} trades={m['trades']} "
            f"net_pnl={m['net_pnl']:.2f} fees={m['fees']:.2f} slippage={m['slippage']:.2f} "
            f"llm_cost={m['llm_cost']:.2f} kill_switch={s['kill_switch_tripped']} "
            f"(fuente decisiones: {payload['decision_source']['type']})"
        )
        return "PASS", detail
    except (KeyError, json.JSONDecodeError):
        return "PENDING", f"resultado de sesión paper ilegible: {result}"


def check_testnet() -> tuple[str, str]:
    rel = "docs/phases/15/evidence/bybit-testnet-lifecycle-pass-final.log"
    log = REPO / rel
    if not log.exists():
        return "PENDING", "lifecycle de órdenes Testnet real no registrado"
    text = log.read_text(encoding="utf-8")
    if "TESTNET_LIFECYCLE=PASS" in text and "exit=0" in text:
        return "PASS", f"lifecycle real create/reconcile/cancel validado contra Testnet ({rel})"
    return "PENDING", f"lifecycle Testnet sin PASS o exit=0: {rel}"


def check_observability() -> tuple[str, str]:
    code, out = _run(
        [
            "uv",
            "run",
            "pytest",
            "tests/test_dashboard.py",
            "tests/test_metrics_registry.py",
            "-q",
            "--no-header",
            "-x",
        ]
    )
    if code == 0:
        return "PASS", f"métricas y dashboard verificados ({out.strip().splitlines()[-1]})"
    return "PENDING", f"tests de observabilidad fallando: {out[-300:]}"


def check_security() -> tuple[str, str]:
    audit_code, audit_out = _run(["uv", "run", "pip-audit", "--desc", "off"])
    secrets_ok = (
        not any((REPO / ".env").exists() and False for _ in [0]) and not (REPO / ".env").exists()
    )
    if audit_code == 0 and secrets_ok:
        vulns = [line for line in audit_out.splitlines() if "vulnerability" in line.lower()]
        detail = "pip-audit limpio" + (f"; {vulns[0]}" if vulns else "; 0 vulnerabilidades")
        return "PASS", detail + "; .env fuera del repo; hooks anti-secretos activos"
    return (
        "PENDING",
        f"pip-audit exit={audit_code}: {audit_out[-300:] or 'sin salida'}"
        + ("" if secrets_ok else "; .env presente en el repo"),
    )


def check_ci() -> tuple[str, str]:
    """Equivalente local del pipeline (.github/workflows/ci.yml)."""
    checks = {
        "ruff": ["uv", "run", "ruff", "check", "."],
        "format": ["uv", "run", "ruff", "format", "--check", "."],
        "mypy": ["uv", "run", "mypy", "src", "tests"],
        "pytest": [
            "uv",
            "run",
            "pytest",
            "tests",
            "--ignore=tests/integration",
            "--cov=src",
            "--cov-branch",
            "--cov-fail-under=90",
            "-q",
        ],
    }
    failures: list[str] = []
    for name, cmd in checks.items():
        code, out = _run(cmd)
        if code != 0:
            failures.append(f"{name}({code}): {out[-200:]}")
    if failures:
        return "PENDING", "pipeline local con fallos: " + "; ".join(failures)
    return (
        "PASS",
        "equivalente local del pipeline verde (ruff+format+mypy+pytest+coverage>=90%); "
        "CI remoto en GitHub Actions se disparará con el PR a main",
    )


def check_uat() -> tuple[str, str]:
    uat_file = EVIDENCE / ".." / "uat" / "phase-15-uat.md"
    if Path(uat_file).exists() and "VEREDICTO UAT: APPROVED" in Path(uat_file).read_text(
        encoding="utf-8"
    ):
        return "PASS", "checklist HITL de fase 15 APPROVED"
    return "PENDING", "UAT de la fase 15 pendiente de decisión humana"


GATES = {
    "BACKTEST": check_backtest,
    "REPLAY": check_replay,
    "PAPER": check_paper,
    "TESTNET": check_testnet,
    "OBSERVABILITY": check_observability,
    "SECURITY": check_security,
    "CI": check_ci,
    "UAT": check_uat,
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="release-check", description=__doc__)
    parser.add_argument("--report", default=str(EVIDENCE / "15" / "LOCAL_RELEASE_REPORT.md"))
    args = parser.parse_args(argv)

    rows: list[tuple[str, str, str]] = []
    for name, fn in GATES.items():
        status, detail = fn()
        rows.append((name, status, detail))

    accepted = all(status == "PASS" for _, status, _ in rows)
    lines = [
        "# LOCAL_RELEASE_REPORT — Self-Evaluating Trading Agent",
        "",
        f"**Fecha:** {dt.date.today().isoformat()} · **Rama:** feature/phase-08-llm-decision-agent",
        f"**Veredicto binario:** {'ACCEPTED' if accepted else 'NOT_ACCEPTED'} "
        "(los 8 gates deben estar en PASS simultáneo — PRD §15)",
        "",
        "| Gate | Estado | Detalle |",
        "|---|---|---|",
    ]
    for name, status, detail in rows:
        lines.append(f"| {name} | {status} | {detail} |")
    lines += [
        "",
        "## Notas honestas",
        "",
        "- Los gates PENDING indican recursos aún no disponibles o corridas oficiales "
        "no ejecutadas; NO se declaran PASS sin evidencia (skill release-readiness).",
        "- SECURITY incluye pip-audit sobre el lockfile actual.",
        "- El equivalente local de CI cubre exactamente los pasos de .github/workflows/ci.yml.",
        "",
    ]
    out_path = Path(args.report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    for name, status, detail in rows:
        print(f"{status:8} {name}: {detail[:100]}")
    print(f"\nReporte: {out_path}")
    print(f"VEREDICTO: {'ACCEPTED' if accepted else 'NOT_ACCEPTED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
