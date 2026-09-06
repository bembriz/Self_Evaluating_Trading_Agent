import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeGuard

MIN_DAYS = 30
MIN_TRADES = 200
MIN_REGIMES = 2


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def invalidate_state(
    state: dict[str, Any],
    *,
    reason: str,
    invalidated_at_ms: int,
) -> dict[str, Any]:
    """Devuelve una copia del estado marcada INVALIDATED (para archivar la corrida).

    No muta el diccionario original: la copia conserva toda la métrica acumulada
    (auditable) y añade status/motivo/timestamp de invalidación.
    """
    archived = dict(state)
    archived["status"] = "INVALIDATED"
    archived["invalidated_reason"] = reason
    archived["invalidated_at_ms"] = invalidated_at_ms
    return archived


def reset_certification_state(state: dict[str, Any]) -> dict[str, Any]:
    """Estado limpio para una nueva corrida con la MISMA versión de estrategia.

    La corrida invalidada no puede arrastrar días/trades/regímenes/reportes a la
    certificación siguiente; se conservan strategy_version/hash para que el hash
    activo siga coincidiendo con el código desplegado.
    """
    strategy_hash = state.get("strategy_hash")
    if not isinstance(strategy_hash, str):
        strategy_hash = state.get("active_strategy_hash", "")
    return {
        "strategy_version": state.get("strategy_version", ""),
        "strategy_hash": strategy_hash,
        "active_strategy_hash": strategy_hash,
        "calendar_days": 0,
        "trade_count": 0,
        "market_regimes": [],
        "periodic_reports": [],
    }


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
    if state.get("status") == "INVALIDATED":
        reason = state.get("invalidated_reason")
        if isinstance(reason, str) and reason:
            return CertificationResult("INVALIDATED", [f"invalidated: {reason}"])
        return CertificationResult("INVALIDATED", ["invalidated by operator"])

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
    parser.add_argument(
        "--invalidate",
        action="store_true",
        help="Mark the run INVALIDATED (archive copy + reset active state for a new run).",
    )
    parser.add_argument("--reason", default="", help="Reason for invalidation (with --invalidate).")
    parser.add_argument("--archive", default="", help="Path to write the INVALIDATED snapshot.")
    args = parser.parse_args(argv)

    state_path = Path(args.state)
    report_path = Path(args.report)

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: corrupt certification state JSON: {exc}", file=sys.stderr)
        return 2

    if args.invalidate:
        if not args.reason.strip():
            print("ERROR: --reason is required with --invalidate", file=sys.stderr)
            return 2
        if not args.archive.strip():
            print("ERROR: --archive is required with --invalidate", file=sys.stderr)
            return 2
        archived = invalidate_state(
            state,
            reason=args.reason.strip(),
            invalidated_at_ms=int(time.time() * 1000),
        )
        _write_json_atomic(Path(args.archive), archived)
        _write_json_atomic(state_path, reset_certification_state(state))
        report_state: dict[str, Any] = archived
    else:
        report_state = state

    result = evaluate_state(report_state)
    calendar_days = int(report_state.get("calendar_days", 0))
    trade_count = int(report_state.get("trade_count", 0))
    market_regimes = report_state.get("market_regimes", [])
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
