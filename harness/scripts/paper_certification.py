import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIN_DAYS = 30
MIN_TRADES = 200
MIN_REGIMES = 2


@dataclass(frozen=True)
class CertificationResult:
    status: str
    reasons: list[str]


def evaluate_state(state: dict[str, Any]) -> CertificationResult:
    if state.get("strategy_hash") != state.get("active_strategy_hash"):
        return CertificationResult(
            status="INVALIDATED",
            reasons=["strategy hash changed"],
        )

    reasons: list[str] = []
    calendar_days = int(state.get("calendar_days", 0))
    trade_count = int(state.get("trade_count", 0))
    market_regimes = state.get("market_regimes", [])
    periodic_reports = state.get("periodic_reports", [])

    regime_count = len(market_regimes) if isinstance(market_regimes, list) else 0
    report_count = len(periodic_reports) if isinstance(periodic_reports, list) else 0
    if isinstance(periodic_reports, list):
        report_count = sum(
            1 for report in periodic_reports if isinstance(report, str) and Path(report).exists()
        )
    else:
        report_count = 0

    if calendar_days < MIN_DAYS:
        reasons.append(f"calendar_days below minimum: {calendar_days} < {MIN_DAYS}")
    if trade_count < MIN_TRADES:
        reasons.append(f"trade_count below minimum: {trade_count} < {MIN_TRADES}")
    if regime_count < MIN_REGIMES:
        reasons.append(f"market_regimes below minimum: {regime_count} < {MIN_REGIMES}")
    if report_count == 0:
        reasons.append("periodic_reports missing")

    if reasons:
        return CertificationResult(status="PENDING", reasons=reasons)
    return CertificationResult(status="PASS", reasons=[])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Phase 16 paper certification state.")
    parser.add_argument("--state", required=True, help="Path to certification state JSON.")
    parser.add_argument("--report", required=True, help="Path to write Markdown report.")
    args = parser.parse_args(argv)

    state_path = Path(args.state)
    report_path = Path(args.report)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: corrupt certification state JSON: {exc}", file=sys.stderr)
        return 2

    result = evaluate_state(state)
    calendar_days = int(state.get("calendar_days", 0))
    trade_count = int(state.get("trade_count", 0))
    market_regimes = state.get("market_regimes", [])
    regime_count = len(market_regimes) if isinstance(market_regimes, list) else 0

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# Paper Certification Report",
                "",
                f"Status: {result.status}",
                "",
                "## Progress",
                "",
                f"- calendar_days {calendar_days}/{MIN_DAYS}",
                f"- trade_count {trade_count}/{MIN_TRADES}",
                f"- market_regimes {regime_count}/{MIN_REGIMES}",
                "",
                "## Reasons",
                "",
                *(f"- {reason}" for reason in result.reasons),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(result.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
