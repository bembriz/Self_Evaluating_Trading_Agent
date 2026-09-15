"""Phase 18D e2e: the 3-strategy evaluation script produces safe, reproducible evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from lab.development_evaluation import classify_development_result

REPO = Path(__file__).resolve().parents[2]
SCRIPT = "harness/scripts/phase18d_development_evaluation.py"
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


@pytest.mark.real_dataset
def test_script_emits_complete_three_strategy_evidence(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    report = _run_script(output)

    assert report["PHASE"] == "18D"
    assert report["EVALUATION"] == "DEVELOPMENT_ECONOMIC_THREE_STRATEGIES"
    assert report["REGIME_SPEC_DIFFERS_FROM_BASELINE"] is True
    assert report["REGIME_SPEC_DIFFERS_FROM_CONTEXT"] is True
    assert report["REPRODUCIBILITY"] == "PASS"
    assert report["EDGE_PRESENT"] == "NOT_EVALUATED_OUT_OF_SAMPLE"
    assert report["STRATEGY_PROMOTABLE"] == "NOT_EVALUATED"
    assert report["WALK_FORWARD_READS"] == 0
    assert report["FINAL_HOLDOUT_READS"] == 0
    assert report["FINAL_HOLDOUT_EXECUTIONS"] == 0
    assert report["HOLDOUT_STATE"] == "PRISTINE"
    assert report["DEVELOPMENT_RESULT"] in {"IMPROVED", "MIXED", "NOT_IMPROVED"}
    assert report["INCREMENTAL_RESULT_VS_CONTEXT"] in {"IMPROVED", "MIXED", "NOT_IMPROVED"}
    assert report["WALK_FORWARD_CANDIDATE"] in {"YES", "NO"}

    # Predeclared classification is reproduced from the recorded metrics.
    assert report["DEVELOPMENT_RESULT"] == classify_development_result(
        report["BASELINE"], report["BTC_REGIME"]
    )
    assert report["INCREMENTAL_RESULT_VS_CONTEXT"] == classify_development_result(
        report["BTC_CONTEXT"], report["BTC_REGIME"]
    )

    attribution = report["BTC_FILTER_ATTRIBUTION"]
    assert attribution["BASELINE_BUY_CANDIDATES"] == (
        attribution["REGIME_CONFIRMED_BUYS"] + attribution["REGIME_BLOCKED_BUYS"]
    )
    assert attribution["ADDITIONAL_BUYS_BLOCKED_BY_SLOPE"] == (
        attribution["CONTEXT_CONFIRMED_BUYS"] - attribution["REGIME_CONFIRMED_BUYS"]
    )
    assert attribution["CONTEXT_CONFIRMED_BUYS"] >= attribution["REGIME_CONFIRMED_BUYS"]

    payload = json.loads((output / "development-comparison.json").read_text(encoding="utf-8"))
    assert payload == report
    markdown = (output / "development-comparison.md").read_text(encoding="utf-8")
    assert "| Metric | baseline-v1 | EmaRsiBtcContext-v1 | EmaRsiBtcRegime-v1 |" in markdown
    assert "BTC filter attribution" in markdown

    registry = output / "registry"
    for spec_id_value in (
        report["BASELINE_SPEC_ID"],
        report["CONTEXT_SPEC_ID"],
        report["REGIME_SPEC_ID"],
    ):
        assert (registry / spec_id_value / "spec.json").is_file()


@pytest.mark.real_dataset
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
