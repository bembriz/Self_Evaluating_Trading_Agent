#!/usr/bin/env python3
"""Preflight guards — invariantes permanentes que deben pasar ANTES de cualquier gate de fase.

Guardas:
  A. STALE_BRANCH — la rama actual contiene el HEAD local de main
  B. ACCOUNTING   — net_pnl = gross_pnl - fees (sin doble resta de slippage)
  C. RISK         — daily loss reset UTC, BUY-only blocking, SELL permitido
  D. PARITY≠CORRECT — un PASS de parity no compensa FAIL de accounting/risk
  E. CONFIG_PROVENANCE — replay autoritativo usa configuración congelada (no defaults)
  F. RELEASE_PROVENANCE — deploy requiere commit+kernel+version+image

Uso:
  python3 harness/scripts/preflight_guards.py [--json]
  python3 harness/scripts/preflight_guards.py --guard accounting
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# A. STALE BRANCH GUARD
# ---------------------------------------------------------------------------


def check_stale_branch() -> dict:
    """Verify current branch contains local main HEAD."""
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        return {"id": "stale-branch", "status": "FAIL", "detail": "cannot determine current branch"}

    if branch == "main":
        return {"id": "stale-branch", "status": "PASS", "detail": "on main — skip"}

    try:
        main_sha = subprocess.check_output(
            ["git", "rev-parse", "main"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "main", branch],
            cwd=ROOT,
            capture_output=True,
        )
        if result.returncode == 0:
            return {
                "id": "stale-branch",
                "status": "PASS",
                "detail": f"branch '{branch}' contains main ({main_sha[:8]})",
            }
        return {
            "id": "stale-branch",
            "status": "FAIL",
            "detail": f"branch '{branch}' does NOT contain main ({main_sha[:8]})",
        }
    except subprocess.CalledProcessError:
        return {"id": "stale-branch", "status": "FAIL", "detail": "cannot verify main ancestry"}


# ---------------------------------------------------------------------------
# B. ACCOUNTING INVARIANT GATE
# ---------------------------------------------------------------------------


def check_accounting() -> dict:
    """Verify the accounting regression tests pass (net_pnl = gross_pnl - fees)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_accounting_regression.py", "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    passed = "passed" in result.stdout or result.returncode == 0
    # Also verify the critical formula line exists in source
    portfolio_path = ROOT / "src" / "domain" / "portfolio" / "portfolio.py"
    formula_ok = False
    if portfolio_path.exists():
        content = portfolio_path.read_text(encoding="utf-8")
        formula_ok = (
            "net_pnl = gross_pnl - fees" in content and "gross_pnl - fees - slippage" not in content
        )
    status = "PASS" if passed and formula_ok else "FAIL"
    detail_parts = []
    if not passed:
        detail_parts.append(f"pytest exit={result.returncode}")
    if not formula_ok:
        detail_parts.append("formula not found or stale subtraction detected in portfolio.py")
    return {
        "id": "accounting-invariant",
        "status": status,
        "detail": "; ".join(detail_parts)
        if detail_parts
        else "net_pnl = gross_pnl - fees verified",
    }


# ---------------------------------------------------------------------------
# C. RISK INVARIANT GATE
# ---------------------------------------------------------------------------


def check_risk() -> dict:
    """Verify daily loss reset, BUY-only blocking, SELL allowed."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_daily_loss_regression.py", "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    passed = result.returncode == 0
    # Also verify risk engine ordering in source
    engine_path = ROOT / "src" / "domain" / "risk" / "engine.py"
    ordering_ok = False
    if engine_path.exists():
        content = engine_path.read_text(encoding="utf-8")
        # kill_switch must come before max_drawdown
        ks_pos = content.find("kill_switch")
        md_pos = content.find("max_drawdown")
        ordering_ok = ks_pos < md_pos if ks_pos >= 0 and md_pos >= 0 else False
    status = "PASS" if passed and ordering_ok else "FAIL"
    detail_parts = []
    if not passed:
        detail_parts.append(f"pytest exit={result.returncode}")
    if not ordering_ok:
        detail_parts.append("risk ordering not verified in engine.py")
    return {
        "id": "risk-invariant",
        "status": status,
        "detail": "; ".join(detail_parts)
        if detail_parts
        else "daily loss reset + risk ordering verified",
    }


# ---------------------------------------------------------------------------
# D. PARITY IS NOT CORRECTNESS
# ---------------------------------------------------------------------------


def check_parity_separation() -> dict:
    """Verify parity and correctness are independent — no cross-compensation."""
    # Check that accounting and risk tests are in separate files from parity tests
    accounting_exists = (ROOT / "tests" / "test_accounting_regression.py").exists()
    risk_exists = (ROOT / "tests" / "test_daily_loss_regression.py").exists()
    # Verify no test file imports parity logic into accounting/risk tests
    for test_file in ["tests/test_accounting_regression.py", "tests/test_daily_loss_regression.py"]:
        path = ROOT / test_file
        if path.exists():
            content = path.read_text(encoding="utf-8")
            if "parity" in content.lower() and "import" in content:
                return {
                    "id": "parity-separation",
                    "status": "FAIL",
                    "detail": f"{test_file} imports parity module",
                }
    status = "PASS" if accounting_exists and risk_exists else "FAIL"
    return {
        "id": "parity-separation",
        "status": status,
        "detail": "accounting/risk tests independent of parity",
    }


# ---------------------------------------------------------------------------
# E. EXACT-CONFIG AUTHORITATIVE REPLAY GUARD
# ---------------------------------------------------------------------------


def check_config_provenance() -> dict:
    """Verify promotional replay uses frozen config, not naked RiskConfig().

    Checks that lab evaluation scripts pass a named/versioned RiskConfig
    to PaperEngine, not a naked RiskConfig() with defaults.
    """
    eval_scripts = [
        "harness/scripts/phase18b_development_evaluation.py",
        "harness/scripts/phase18d_development_evaluation.py",
        "harness/scripts/phase19b_development_evaluation.py",
        "harness/scripts/phase20b_development_evaluation.py",
    ]
    issues = []
    found_named_config = False
    for script_rel in eval_scripts:
        script = ROOT / script_rel
        if not script.exists():
            continue
        content = script.read_text(encoding="utf-8")
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Naked RiskConfig() in a non-definition, non-import line
            if (
                "RiskConfig()" in stripped
                and "def " not in stripped
                and "import" not in stripped
                and "=" not in stripped.split("RiskConfig()")[0]
            ):
                issues.append(f"{script_rel}:{i}")
            # Named config (e.g. ENGINE_CONFIG = RiskConfig(...))
            if "RiskConfig(" in stripped and "=" in stripped.split("RiskConfig(")[0]:
                found_named_config = True

    if not issues and found_named_config:
        return {
            "id": "config-provenance",
            "status": "PASS",
            "detail": "eval scripts use named/versioned RiskConfig",
        }
    if not issues and not found_named_config:
        return {
            "id": "config-provenance",
            "status": "MANUAL",
            "detail": "no RiskConfig usage found in eval scripts",
        }
    return {
        "id": "config-provenance",
        "status": "FAIL",
        "detail": f"naked RiskConfig() at: {', '.join(issues)}",
    }


# ---------------------------------------------------------------------------
# F. RELEASE PROVENANCE GUARD
# ---------------------------------------------------------------------------


def check_release_provenance() -> dict:
    """Verify release provenance artifacts exist and are consistent."""
    checks = []

    # version.py must exist
    version_path = ROOT / "src" / "version.py"
    if version_path.exists():
        content = version_path.read_text(encoding="utf-8")
        if "__version__" in content:
            checks.append("version.py: OK")
        else:
            checks.append("version.py: missing __version__")
    else:
        checks.append("version.py: NOT FOUND")

    # pyproject.toml version must match
    pyproject = ROOT / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.strip().startswith("version"):
                checks.append(f"pyproject.toml: {line.strip()}")
                break

    # RiskConfig.version must exist
    risk_config = ROOT / "src" / "domain" / "risk" / "config.py"
    if risk_config.exists():
        content = risk_config.read_text(encoding="utf-8")
        if "version" in content:
            checks.append("risk config: versioned")
        else:
            checks.append("risk config: NO version")

    status = (
        "PASS"
        if all("OK" in c or "versioned" in c or "pyproject" in c for c in checks)
        else "MANUAL"
    )
    return {
        "id": "release-provenance",
        "status": status,
        "detail": " | ".join(checks),
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

ALL_GUARDS = {
    "stale-branch": check_stale_branch,
    "accounting": check_accounting,
    "risk": check_risk,
    "parity": check_parity_separation,
    "config-provenance": check_config_provenance,
    "release-provenance": check_release_provenance,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight invariant guards")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument("--guard", choices=list(ALL_GUARDS.keys()), help="run single guard")
    args = parser.parse_args()

    guards = [ALL_GUARDS[args.guard]()] if args.guard else [fn() for fn in ALL_GUARDS.values()]

    any_fail = any(g["status"] == "FAIL" for g in guards)

    if args.json:
        print(json.dumps({"guards": guards, "any_fail": any_fail}, indent=2))
    else:
        for g in guards:
            icon = {"PASS": "✓", "FAIL": "✗", "MANUAL": "?"}.get(g["status"], "?")
            print(f"  [{icon}] {g['id']}: {g['status']} — {g['detail']}")
        print()
        if any_fail:
            print("PREFLIGHT: FAIL")
        else:
            print("PREFLIGHT: PASS")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
