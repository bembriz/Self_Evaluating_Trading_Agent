#!/usr/bin/env python3
"""Phase 22-A — Generate exit-reason-analysis.csv from authoritative data.

Reads exit-reason-analysis.json and generates a CSV with corrected exit reason labels.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
JSON_PATH = REPO / "docs" / "phases" / "22" / "evidence" / "exit-reason-analysis.json"
CSV_PATH = REPO / "docs" / "phases" / "22" / "evidence" / "exit-reason-analysis.csv"

# Corrected label mapping
LABEL_MAP = {
    "stop_loss": "FALLBACK_NEAR_ENTRY_STOP",
    "llm_sell": "STRATEGY_SIGNAL_EXIT",
    "take_profit": "TAKE_PROFIT",
    "trailing_stop": "TRAILING_STOP",
    "UNKNOWN": "UNKNOWN",
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text())

    rows = []
    for strategy_name, strategy_data in data["strategies"].items():
        total_trades = strategy_data["completed_trades"]
        exit_counts = strategy_data["exit_reason_counts"]

        # Get exit reason analysis for this strategy
        analysis = data["exit_reason_analysis"].get(strategy_name, {})

        # Calculate metrics for each exit reason
        for raw_reason in ["stop_loss", "llm_sell", "take_profit", "trailing_stop", "UNKNOWN"]:
            corrected_reason = LABEL_MAP.get(raw_reason, raw_reason)

            if raw_reason in exit_counts:
                count = exit_counts[raw_reason]
                rate = count / total_trades if total_trades > 0 else 0

                # Get detailed analysis if available
                if raw_reason in analysis:
                    a = analysis[raw_reason]
                    avg_net_pnl = a.get("avg_net_corrected", 0)
                    total_net_pnl = a.get("total_net_pnl", 0)
                    avg_holding_bars = a.get("avg_holding_bars", 0)
                    median_holding_bars = a.get("median_holding_bars", 0)
                    avg_return_bps = a.get("avg_return_bps", 0)
                else:
                    avg_net_pnl = 0
                    total_net_pnl = 0
                    avg_holding_bars = 0
                    median_holding_bars = 0
                    avg_return_bps = 0

                rows.append({
                    "strategy": strategy_name,
                    "exit_reason": corrected_reason,
                    "count": count,
                    "rate": f"{rate:.6f}",
                    "total_trades": total_trades,
                    "avg_net_pnl": f"{avg_net_pnl:.6f}",
                    "total_net_pnl": f"{total_net_pnl:.6f}",
                    "avg_holding_bars": f"{avg_holding_bars:.1f}",
                    "median_holding_bars": median_holding_bars,
                    "avg_return_bps": f"{avg_return_bps:.2f}",
                })
            else:
                # Exit reason not present for this strategy
                rows.append({
                    "strategy": strategy_name,
                    "exit_reason": corrected_reason,
                    "count": 0,
                    "rate": "0.000000",
                    "total_trades": total_trades,
                    "avg_net_pnl": "0.000000",
                    "total_net_pnl": "0.000000",
                    "avg_holding_bars": "0.0",
                    "median_holding_bars": 0,
                    "avg_return_bps": "0.00",
                })

    # Write CSV
    fieldnames = [
        "strategy", "exit_reason", "count", "rate", "total_trades",
        "avg_net_pnl", "total_net_pnl", "avg_holding_bars", "median_holding_bars",
        "avg_return_bps"
    ]

    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {CSV_PATH}")
    print(f"Total rows: {len(rows)}")

    # Print summary
    print("\nExit Reason Analysis Summary (Corrected Labels):")
    print("=" * 80)
    for row in rows:
        if row["count"] > 0:
            print(f"{row['strategy']:12s} | {row['exit_reason']:25s} | "
                  f"count={row['count']:4d} | rate={row['rate']:6s} | "
                  f"avg_net_pnl={row['avg_net_pnl']:10s} | "
                  f"total_net_pnl={row['total_net_pnl']:12s}")


if __name__ == "__main__":
    main()
