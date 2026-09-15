"""Phase 18B e2e: the evaluation script produces reproducible, safe evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = "harness/scripts/phase18b_development_evaluation.py"
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
def test_script_emits_complete_development_evidence(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    report = _run_script(output)

    assert report["PHASE"] == "18B"
    assert report["EVALUATION"] == "DEVELOPMENT_ECONOMIC"
    assert report["SPEC_IDS_DIFFERENT"] is True
    assert report["REPRODUCIBILITY"] == "PASS"
    assert report["EDGE_PRESENT"] == "NOT_EVALUATED_OUT_OF_SAMPLE"
    assert report["STRATEGY_PROMOTABLE"] == "NOT_EVALUATED"
    assert report["WALK_FORWARD_READS"] == 0
    assert report["FINAL_HOLDOUT_READS"] == 0
    assert report["FINAL_HOLDOUT_EXECUTIONS"] == 0
    assert report["HOLDOUT_STATE"] == "PRISTINE"
    assert report["DEVELOPMENT_RESULT"] in {"IMPROVED", "MIXED", "NOT_IMPROVED"}
    assert report["WALK_FORWARD_CANDIDATE"] in {"YES", "NO"}

    attribution = report["BTC_FILTER_ATTRIBUTION"]
    assert (
        attribution["baseline_buy_candidates"]
        == attribution["btc_confirmed_buys"] + attribution["btc_blocked_buys"]
    )

    payload = json.loads((output / "development-comparison.json").read_text(encoding="utf-8"))
    assert payload == report
    markdown = (output / "development-comparison.md").read_text(encoding="utf-8")
    assert "| Metric | baseline-v1 | EmaRsiBtcContext-v1 | delta |" in markdown
    assert "BTC filter attribution" in markdown

    registry = output / "registry"
    assert (registry / report["BASELINE_SPEC_ID"] / "spec.json").is_file()
    assert (registry / report["BTC_CONTEXT_SPEC_ID"] / "spec.json").is_file()
    assert (
        registry / report["BTC_CONTEXT_SPEC_ID"] / "runs" / "18b-candidate-run-1.json"
    ).is_file()
    assert (
        registry / report["BTC_CONTEXT_SPEC_ID"] / "runs" / "18b-candidate-run-2.json"
    ).is_file()


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
