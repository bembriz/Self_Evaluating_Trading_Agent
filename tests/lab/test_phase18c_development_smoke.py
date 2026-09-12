"""Executable contract for the Phase 18C DEVELOPMENT-only smoke."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_smoke_counts_official_development_strategy_decisions() -> None:
    proc = subprocess.run(
        [sys.executable, "harness/scripts/phase18c_development_smoke.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["COUNTER_UNIT"] == "strategy_decisions"
    assert result["BASELINE_BUY_SIGNALS"] == (
        result["BTC_REGIME_BUY_SIGNALS"] + result["BTC_BLOCKED_BUYS"]
    )
    assert result["BTC_BLOCKED_BUYS"] > 0
    assert result["REQUESTED_RANGES"] == [
        {"row_end": 5000, "row_start": 0, "symbol": "ETHUSDT"},
        {"row_end": 5000, "row_start": 0, "symbol": "BTCUSDT"},
    ]
    assert result["FINAL_HOLDOUT_READS"] == 0
    assert result["FINAL_HOLDOUT_EXECUTIONS"] == 0
