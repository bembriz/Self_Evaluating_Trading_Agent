import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

MIN_DAYS = 30
MIN_TRADES = 200
MIN_REGIMES = 2


@dataclass(frozen=True)
class CertificationResult:
    status: str
    reasons: list[str]


def _is_valid_regime_evidence(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    required_strings = ("name", "symbol", "timeframe", "classifier_version")
    if not all(isinstance(value.get(key), str) and value[key] for key in required_strings):
        return False
    confirmation_candles = value.get("confirmation_candles")
    if not isinstance(confirmation_candles, int) or confirmation_candles < 3:
        return False
    first_seen_at_ms = value.get("first_seen_at_ms")
    confirmed_at_ms = value.get("confirmed_at_ms")
    last_seen_at_ms = value.get("last_seen_at_ms")
    if not isinstance(first_seen_at_ms, int) or first_seen_at_ms < 0:
        return False
    if not isinstance(confirmed_at_ms, int) or confirmed_at_ms < 0:
        return False
    if not isinstance(last_seen_at_ms, int) or last_seen_at_ms < 0:
        return False
    return first_seen_at_ms <= confirmed_at_ms <= last_seen_at_ms


def _confirmed_regime_names(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    names: set[str] = set()
    for item in value:
        if _is_valid_regime_evidence(item):
            name = item["name"]
            if isinstance(name, str):
                names.add(name)
    return names


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

    regime_count = len(_confirmed_regime_names(market_regimes))
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
    regime_count = len(_confirmed_regime_names(market_regimes))

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
