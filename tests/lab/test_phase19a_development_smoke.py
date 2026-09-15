"""Executable contract for the Phase 19A DEVELOPMENT-only smoke."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.real_dataset


def test_smoke_exercises_all_paths_and_adx_readiness() -> None:
    proc = subprocess.run(
        [sys.executable, "harness/scripts/phase19a_development_smoke.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["COUNTER_UNIT"] == "strategy_decisions"
    assert result["FIRST_ADX_INDEX"] == 27
    assert result["SIGNALS_BUY"] > 0
    assert result["SIGNALS_SELL"] > 0
    assert result["SIGNALS_HOLD"] > 0
    assert result["REQUESTED_RANGES"] == [{"row_end": 5000, "row_start": 0, "symbol": "ETHUSDT"}]
    assert result["FINAL_HOLDOUT_READS"] == 0
    assert result["FINAL_HOLDOUT_EXECUTIONS"] == 0
