"""Phase 20B e2e: the baseline vs Bollinger evaluation script emits safe evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from lab.development_evaluation import classify_development_result
from lab.viability import AbsoluteViabilityEvidence, walk_forward_eligible

REPO = Path(__file__).resolve().parents[2]
SCRIPT = "harness/scripts/phase20b_development_evaluation.py"
ROW_END = 512


def _run_script(output_dir: Path, *, row_start: int = 0, row_end: int = ROW_END) -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            SCRIPT,
            "--row-start",
            str(row_start),
            "--row-end",
            str(row_end),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report: dict[str, Any] = json.loads(proc.stdout)
    return report


def _viability(report: dict[str, Any]) -> AbsoluteViabilityEvidence:
    return AbsoluteViabilityEvidence(
        net_pnl=report["BOLLINGER"]["net_pnl"],
        expectancy=report["BOLLINGER"]["expectancy"],
        profit_factor=report["BOLLINGER"]["profit_factor"],
    )


def test_script_emits_complete_comparison_evidence(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    report = _run_script(output)

    assert report["PHASE"] == "20B"
    assert report["EVALUATION"] == "DEVELOPMENT_ECONOMIC"
    assert report["SPEC_IDS_DIFFERENT"] is True
    assert report["REPRODUCIBILITY"] == "PASS"
    assert report["EDGE_PRESENT"] == "NOT_EVALUATED_OUT_OF_SAMPLE"
    assert report["STRATEGY_PROMOTABLE"] == "NOT_EVALUATED"
    assert report["WALK_FORWARD_AUTHORIZED"] == "NO"
    assert report["WALK_FORWARD_READS"] == 0
    assert report["FINAL_HOLDOUT_READS"] == 0
    assert report["FINAL_HOLDOUT_EXECUTIONS"] == 0
    assert report["HOLDOUT_STATE"] == "PRISTINE"
    assert report["DEVELOPMENT_RESULT"] in {"IMPROVED", "MIXED", "NOT_IMPROVED"}

    # Relative classification and Phase 19C gate reproduced from recorded metrics.
    assert report["DEVELOPMENT_RESULT"] == classify_development_result(
        report["BASELINE"], report["BOLLINGER"]
    )
    evidence = _viability(report)
    assert report["ABSOLUTE_VIABILITY"]["ABSOLUTE_VIABILITY_GATE"] == (
        "PASS" if evidence.passed else "FAIL"
    )
    assert report["WALK_FORWARD_ELIGIBLE"] == (
        "YES" if walk_forward_eligible(report["DEVELOPMENT_RESULT"], evidence) else "NO"
    )

    diagnostics = report["MEAN_REVERSION_DIAGNOSTICS"]
    assert diagnostics["REENTRY_EVENTS"] == (
        diagnostics["REENTRIES_CONFIRMED_LOW_ADX"] + diagnostics["REENTRIES_BLOCKED_BY_ADX"]
    )
    assert diagnostics["SELL_PRECEDENCE_EVENTS"] <= diagnostics["SIMULTANEOUS_BUY_SELL_SETUPS"]

    attribution = report["SIGNAL_EXECUTION_ATTRIBUTION"]
    assert attribution["BUY_SIGNALS"] == (
        diagnostics["REENTRIES_CONFIRMED_LOW_ADX"] - diagnostics["SIMULTANEOUS_BUY_SELL_SETUPS"]
    )
    assert attribution["BUY_SIGNALS"] == (
        attribution["EXECUTED_BUYS"] + attribution["REJECTED_BUYS"] + attribution["SUPERSEDED_BUYS"]
    )

    payload = json.loads((output / "development-comparison.json").read_text(encoding="utf-8"))
    assert payload == report
    markdown = (output / "development-comparison.md").read_text(encoding="utf-8")
    assert "| Metric | baseline-v1 | EthBollingerMeanReversion-v1 | Delta |" in markdown
    assert "Absolute viability" in markdown
    assert "Mean-reversion diagnostics" in markdown
    assert "Baseline behavior anchor" in markdown

    registry = output / "registry"
    assert (registry / report["BASELINE_SPEC_ID"] / "spec.json").is_file()
    assert (registry / report["BOLLINGER_SPEC_ID"] / "spec.json").is_file()
    assert (registry / report["BOLLINGER_SPEC_ID"] / "runs" / "20b-bollinger-run-2.json").is_file()


def test_script_is_deterministic(tmp_path: Path) -> None:
    first = _run_script(tmp_path / "run-a")
    second = _run_script(tmp_path / "run-b")
    assert first == second


def test_script_rejects_walk_forward_and_holdout_ranges(tmp_path: Path) -> None:
    for row_start, row_end in ((62208, 62300), (88128, 88200)):
        proc = subprocess.run(
            [
                sys.executable,
                SCRIPT,
                "--row-start",
                str(row_start),
                "--row-end",
                str(row_end),
                "--output-dir",
                str(tmp_path / f"reject-{row_start}"),
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode != 0
        assert "DEVELOPMENT" in proc.stderr
