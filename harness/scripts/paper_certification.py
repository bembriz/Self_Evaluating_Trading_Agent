"""Paper Certification Gate (fase 16c.4) — evaluador operacional determinista.

Separa la **certificación Paper** (integridad operacional) de la validación
estadística (Replay / walk-forward / holdout). Este módulo evalúa SOLO los
criterios operacionales; NO exige número de trades, Profit Factor, Sharpe,
Sortino, expectancy ni significancia estadística.

Semántica de fills/trades (documentada, NO criterio de gate):

- ``fill_count``        → número de fills (eventos con ``filled=True``).
- ``closed_trade_count``→ número de trades cerrados (derivable del portfolio).
- ``trade_count``       → alias legacy de ``fill_count`` (el runner 0.1.x lo
  escribe como ``summary.fills``). Se conserva por compatibilidad de lectura;
  NO se usa como criterio de certificación.

Regla de estado: un fallo obligatorio produce ``overall_status = FAIL``. No hay
promedio de criterios ni compensación entre ellos. El estado histórico previo
se conserva como ``INVALIDATED`` (no se borra ni reescribe).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CERTIFICATION_WINDOW_DAYS = 30
SECONDS_PER_DAY = 86_400

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_INVALIDATED = "INVALIDATED"

# Contrato de congelamiento de versión/hash. ``certification_started_at`` ancla
# el reloj de 30 días y además es un campo congelado: si deriva, el reloj NO se
# re-ancla silenciosamente y el gate falla por drift de versiones.
FROZEN_VERSION_KEYS = (
    "git_commit",
    "application_version",
    "strategy_version",
    "risk_config_version",
    "docker_image_digest",
    "symbol",
    "timeframe",
    "initial_capital",
    "fees_slippage_config_version",
    "certification_started_at",
)


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _to_epoch_seconds(value: object) -> float | None:
    """Convierte un timestamp a epoch en segundos UTC.

    Acepta ISO-8601 con sufijo ``Z`` (o offset explícito) y epoch en
    **milisegundos** (convención del codebase: ``*_at_ms``).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return None
    return None


def _format_iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_pass(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in ("PASS", "TRUE", "YES", "1", "OK")
    return False


def _normalize_version_value(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value.strip()
    return value


def _frozen_version_drift(frozen: Mapping[str, object], current: Mapping[str, object]) -> list[str]:
    return [
        key
        for key in FROZEN_VERSION_KEYS
        if _normalize_version_value(frozen.get(key)) != _normalize_version_value(current.get(key))
    ]


def _certification_age_days(
    frozen: Mapping[str, object], evaluated_at_epoch: float
) -> float | None:
    start = _to_epoch_seconds(frozen.get("certification_started_at"))
    if start is None:
        return None
    return (evaluated_at_epoch - start) / SECONDS_PER_DAY


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


@dataclass(frozen=True, slots=True)
class CertificationCheck:
    name: str
    status: str  # "PASS" | "FAIL"
    observed: object
    required: object
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "observed": self.observed,
            "required": self.required,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class CertificationReport:
    overall_status: str  # "PASS" | "FAIL" | "INVALIDATED"
    evaluated_at: str
    certification_age_days: float | None
    checks: tuple[CertificationCheck, ...]
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_status": self.overall_status,
            "evaluated_at": self.evaluated_at,
            "certification_age_days": self.certification_age_days,
            "checks": [check.to_dict() for check in self.checks],
            "failure_reasons": list(self.failure_reasons),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Paper Certification Report (operational gate)",
            "",
            f"Status: {self.overall_status}",
            f"evaluated_at: {self.evaluated_at}",
            f"certification_age_days: {self.certification_age_days}",
            "",
            "## Checks",
            "",
            "| check | status | observed | required |",
            "|---|---|---|---|",
        ]
        for check in self.checks:
            lines.append(f"| {check.name} | {check.status} | {check.observed} | {check.required} |")
        lines.append("")
        lines.append("## Failure reasons")
        lines.append("")
        if self.failure_reasons:
            lines.extend(f"- {reason}" for reason in self.failure_reasons)
        else:
            lines.append("- (none)")
        lines.append("")
        return "\n".join(lines)


def _make_check(
    name: str,
    passed: bool,
    observed: object,
    required: object,
    evidence: str,
) -> CertificationCheck:
    return CertificationCheck(
        name=name,
        status=STATUS_PASS if passed else STATUS_FAIL,
        observed=observed,
        required=required,
        evidence=evidence,
    )


def _critical_errors_status(errors: object) -> tuple[bool, object]:
    if not isinstance(errors, list):
        return False, "invalid (not a list)"
    explained = 0
    unexplained = 0
    for error in errors:
        if not isinstance(error, Mapping):
            unexplained += 1
            continue
        if error.get("explained") is True:
            explained += 1
        else:
            unexplained += 1
    if unexplained == 0:
        return True, {"total": len(errors), "unexplained": 0}
    return False, {"total": len(errors), "unexplained": unexplained}


def evaluate_certification(
    state: Mapping[str, Any],
    *,
    evaluated_at: str | int | float | None = None,
) -> CertificationReport:
    """Evalúa una certificación Paper con criterios operacionales independientes.

    ``evaluated_at`` (ISO-8601 UTC o epoch ms) fija el instante de evaluación para
    determinismo; por defecto ``now``. La duración real se calcula en UTC entre
    ``frozen.certification_started_at`` y ``evaluated_at``.
    """
    state = state if isinstance(state, Mapping) else {}
    evaluated_epoch = _to_epoch_seconds(evaluated_at) if evaluated_at is not None else time.time()
    if evaluated_epoch is None:
        evaluated_epoch = time.time()
    evaluated_at_iso = _format_iso_utc(evaluated_epoch)

    if state.get("status") == "INVALIDATED":
        reason = state.get("invalidated_reason")
        message = (
            f"invalidated: {reason}"
            if isinstance(reason, str) and reason
            else "invalidated by operator"
        )
        return CertificationReport(
            overall_status=STATUS_INVALIDATED,
            evaluated_at=evaluated_at_iso,
            certification_age_days=_certification_age_days(
                _mapping(state.get("frozen")), evaluated_epoch
            ),
            checks=(),
            failure_reasons=(message,),
        )

    frozen = _mapping(state.get("frozen"))
    current = _mapping(state.get("current"))
    operational = _mapping(state.get("operational"))

    checks: list[CertificationCheck] = []

    age = _certification_age_days(frozen, evaluated_epoch)
    if age is None:
        checks.append(
            _make_check(
                "calendar_days",
                False,
                "missing certification_started_at",
                f">= {CERTIFICATION_WINDOW_DAYS} days",
                "certification_started_at ausente en frozen",
            )
        )
    elif age >= CERTIFICATION_WINDOW_DAYS:
        checks.append(
            _make_check(
                "calendar_days",
                True,
                round(age, 6),
                f">= {CERTIFICATION_WINDOW_DAYS} days",
                f"{round(age, 6)} days >= {CERTIFICATION_WINDOW_DAYS}",
            )
        )
    else:
        checks.append(
            _make_check(
                "calendar_days",
                False,
                round(age, 6),
                f">= {CERTIFICATION_WINDOW_DAYS} days",
                f"{round(age, 6)} days < {CERTIFICATION_WINDOW_DAYS}",
            )
        )

    drift = _frozen_version_drift(frozen, current)
    checks.append(
        _make_check(
            "frozen_versions",
            not drift,
            drift,
            "no drift",
            "version drift: " + ", ".join(drift) if drift else "frozen == current",
        )
    )

    residual = _as_number(operational.get("accounting_residual"))
    checks.append(
        _make_check(
            "accounting_residual",
            residual == 0.0,
            residual,
            0,
            "residual == 0" if residual == 0.0 else f"residual = {residual}",
        )
    )

    for name, human in (
        ("recovery_integrity", "recovery/replay E2E íntegro"),
        ("market_evidence_complete", "velas persistidas sin gaps"),
        ("state_continuity", "portfolio/risk continuos entre reinicios"),
        ("certification_reports_complete", "reportes periódicos completos"),
        ("kill_switch_tested", "kill switch ejercitado"),
        ("daily_loss_tested", "daily-loss ejercitado"),
    ):
        value = operational.get(name)
        checks.append(
            _make_check(
                name,
                _as_pass(value),
                value,
                "PASS",
                f"{human}: {value}",
            )
        )

    gaps = _as_number(operational.get("unexplained_market_gaps"))
    checks.append(
        _make_check(
            "unexplained_market_gaps",
            gaps == 0.0,
            gaps,
            0,
            "sin gaps no explicados" if gaps == 0.0 else f"{gaps} gap(s) sin explicar",
        )
    )

    coverage = _as_number(operational.get("decision_context_coverage"))
    checks.append(
        _make_check(
            "decision_context_coverage",
            coverage is not None and coverage >= 100.0,
            coverage,
            ">= 100%",
            "decision_context en el 100% de eventos"
            if coverage is not None and coverage >= 100.0
            else f"cobertura = {coverage}",
        )
    )

    metrics_days = _as_number(operational.get("metrics_history_days"))
    checks.append(
        _make_check(
            "metrics_history_days",
            metrics_days is not None and metrics_days >= CERTIFICATION_WINDOW_DAYS,
            metrics_days,
            f">= {CERTIFICATION_WINDOW_DAYS} days",
            f"{metrics_days} días de historia de métricas",
        )
    )

    errors_ok, errors_observed = _critical_errors_status(operational.get("critical_errors"))
    checks.append(
        _make_check(
            "critical_errors",
            errors_ok,
            errors_observed,
            "0 or all explained",
            "errores críticos ausentes o todos explicados",
        )
    )

    failures = tuple(check for check in checks if check.status == STATUS_FAIL)
    overall = STATUS_FAIL if failures else STATUS_PASS
    failure_reasons = tuple(f"{check.name}: {check.evidence}" for check in failures)

    return CertificationReport(
        overall_status=overall,
        evaluated_at=evaluated_at_iso,
        certification_age_days=age,
        checks=tuple(checks),
        failure_reasons=failure_reasons,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Phase 16 paper certification (operational gate)."
    )
    parser.add_argument("--state", required=True, help="Path to certification state JSON.")
    parser.add_argument("--report", required=True, help="Path to write Markdown report.")
    parser.add_argument(
        "--json-report", default="", help="Optional path to write machine-readable JSON."
    )
    parser.add_argument(
        "--evaluated-at",
        default="",
        help="Evaluation instant (ISO-8601 UTC or epoch ms). Default: now.",
    )
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
    if not isinstance(state, dict):
        print("ERROR: certification state must be a JSON object", file=sys.stderr)
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

    evaluated_at: str | int | float | None = args.evaluated_at if args.evaluated_at else None
    report = evaluate_certification(report_state, evaluated_at=evaluated_at)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.to_markdown() + "\n", encoding="utf-8")
    if args.json_report:
        _write_json_atomic(Path(args.json_report), report.to_dict())
    print(report.overall_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
