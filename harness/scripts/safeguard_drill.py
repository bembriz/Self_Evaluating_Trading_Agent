"""Safeguard drill del operador — secuencias completas de guards de capital (16c.6 / Task 6).

Antes de iniciar una certificación Paper, el operador ejecuta este drill para
producir evidencia auditable de que los safeguards del producto (kill switch y
daily loss) responden como los consulta el Risk Engine real. Cada drill registra
UNA secuencia completa en ``paper_safeguard_evidence_path`` (por defecto
``docs/phases/16/safeguard-evidence.json``).

Aislamiento y fidelidad (el drill NO introduce caminos especiales en el producto):
- Importa únicamente dominio puro añadiendo ``<repo>/src`` a ``sys.path``;
  nunca importa ``PaperEngine``/``PaperRunner``/``Portfolio``.
- Replica las llamadas exactas que hace el engine: ``RiskEngine.evaluate`` con
  el ``KillSwitchState`` del switch (engine.py:66-69), la rama BUY que consulta
  el daily loss (engine.py:81-83) y la rama SELL reduce que no lo consulta
  (engine.py:75-79). Kill switch: ``KillSwitch.activate/allows_trading/reset`` y
  serialización ``KillSwitchState.to_dict/from_dict`` (guards.py:29-86).
- Daily loss entre reinicios: el producto NO serializa el acumulador
  ``_realized_pnl_today``; ``restore_runner`` re-deriva el estado replanteando
  las velas persistidas (recovery.py:37-50) y el acumulador se rellena por cada
  fill SELL del día y se resetea en el cruce de ``utc_day_index``
  (paper_engine.py:141-146, 227-237; domain/time/day.py:10-12). El drill modela
  esa re-derivación desde los fills del día persistidos (fuente autoritativa).

Escritura crash-safe: tmp + fsync + ``os.replace`` + fsync del directorio;
preserva las entradas de otros kinds. Exit 0 solo si ``status == "PASS"``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Bootstrap de aislamiento: repo root = 3 niveles desde harness/scripts/*.py.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from domain.risk.config import RiskConfig  # noqa: E402
from domain.risk.engine import PortfolioRiskState, RiskEngine, TradeProposal  # noqa: E402
from domain.risk.guards import KillSwitch, KillSwitchState, daily_loss_exceeded  # noqa: E402
from domain.time.day import MS_PER_DAY, utc_day_index  # noqa: E402
from domain.trading.signal import Action, Intensity  # noqa: E402

DEFAULT_EVIDENCE_RELPATH = "docs/phases/16/safeguard-evidence.json"

# Secuencias canónicas: MISMO token y orden que el productor
# (src/application/services/certification_snapshot.py::_SAFEGUARD_DRILL_STEPS).
KILL_SWITCH_STEPS: tuple[str, ...] = (
    "activate",
    "buy_rejected",
    "persist",
    "restart_still_active",
    "buy_still_rejected",
    "operator_reset",
)
DAILY_LOSS_STEPS: tuple[str, ...] = (
    "daily_loss_exceeded",
    "buy_rejected",
    "sell_allowed",
    "restart_persists",
    "utc_rollover_reset",
)
SEQUENCE_STEPS: dict[str, tuple[str, ...]] = {
    "kill_switch": KILL_SWITCH_STEPS,
    "daily_loss": DAILY_LOSS_STEPS,
}

ARTIFACT_KEYS: tuple[str, ...] = (
    "git_commit",
    "application_version",
    "docker_image_digest",
    "strategy_version",
    "risk_config_version",
)


@dataclass(frozen=True, slots=True)
class DrillStepResult:
    """Resultado de un paso: el token canónico + si el comportamiento se cumplió."""

    step: str
    ok: bool
    detail: str


def _iso_utc_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def _now_ms() -> int:
    return int(datetime.now(tz=UTC).timestamp() * 1000)


def _floats_close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def _probe(
    engine: RiskEngine,
    cfg: RiskConfig,
    action: Action,
    *,
    realized: float,
    open_positions: int,
    kill_state: KillSwitchState,
    timestamp_ms: int,
) -> Any:
    """Llama a ``RiskEngine.evaluate`` igual que PaperEngine.on_price (engine.py:157-171)."""
    state = PortfolioRiskState(
        open_positions=open_positions,
        realized_pnl_today=realized,
        peak_equity=cfg.capital,
        equity=cfg.capital,
        kill_switch=kill_state,
    )
    return engine.evaluate(
        TradeProposal(
            action=action,
            intensity=Intensity.MEDIUM,
            price=100.0,
            atr=5.0,
            timestamp_ms=timestamp_ms,
        ),
        state,
    )


def run_kill_switch_drill(*, base_ms: int | None = None) -> tuple[DrillStepResult, ...]:
    """Secuencia completa de kill switch: activar→BUY rechazado→persistir→restart→reset.

    Refleja el producto: el estado se serializa (``KillSwitchState.to_dict``),
    sobrevive un restart (``from_dict``) y solo un reset humano explícito con
    ``approval_id`` lo desactiva (guards.py:77-86). El BUY se rechaza vía el
    mismo camino que consulta el engine: ``RiskEngine.evaluate`` con el
    ``kill_switch.active`` (engine.py:68-69).
    """
    ts = base_ms if base_ms is not None else _now_ms()
    cfg = RiskConfig()
    engine = RiskEngine(cfg)
    steps: list[DrillStepResult] = []

    ks = KillSwitch()
    state = ks.activate(reason="operator safeguard drill", timestamp_ms=ts)
    ok = state.active and state.activated_at_ms == ts and not ks.allows_trading()
    steps.append(
        DrillStepResult(
            "activate", ok, f"active={state.active} allows_trading={ks.allows_trading()}"
        )
    )

    verdict = _probe(
        engine,
        cfg,
        Action.BUY,
        realized=0.0,
        open_positions=0,
        kill_state=ks.state,
        timestamp_ms=ts,
    )
    ok = not verdict.approved and verdict.reason == "kill_switch"
    steps.append(
        DrillStepResult("buy_rejected", ok, f"verdict.reason={verdict.reason} (kill switch activo)")
    )

    serialized = json.dumps(ks.state.to_dict(), sort_keys=True)
    restored_state = KillSwitchState.from_dict(json.loads(serialized))
    ok = restored_state == ks.state and serialized == json.dumps(ks.state.to_dict(), sort_keys=True)
    steps.append(
        DrillStepResult("persist", ok, "to_dict→JSON→from_dict round-trip == estado original")
    )

    restarted = KillSwitch(restored_state)
    ok = restarted.state.active and not restarted.allows_trading()
    steps.append(
        DrillStepResult(
            "restart_still_active",
            ok,
            f"active={restarted.state.active} (KillSwitch desde KillSwitchState.from_dict)",
        )
    )

    verdict = _probe(
        engine,
        cfg,
        Action.BUY,
        realized=0.0,
        open_positions=0,
        kill_state=restarted.state,
        timestamp_ms=ts + 1000,
    )
    ok = not verdict.approved and verdict.reason == "kill_switch"
    steps.append(
        DrillStepResult("buy_still_rejected", ok, f"verdict.reason={verdict.reason} tras restart")
    )

    approval_id = f"drill-kill_switch-{_iso_utc_ms(ts)}"
    restarted.reset(by="human", approval_id=approval_id)
    verdict = _probe(
        engine,
        cfg,
        Action.BUY,
        realized=0.0,
        open_positions=0,
        kill_state=restarted.state,
        timestamp_ms=ts + 2000,
    )
    ok = not restarted.state.active and restarted.allows_trading() and verdict.approved
    steps.append(
        DrillStepResult(
            "operator_reset",
            ok,
            f"reset(by='human', approval_id=...) → active={restarted.state.active}; "
            f"BUY aprobado tras reset (verdict.approved={verdict.approved})",
        )
    )
    return tuple(steps)


def _derived_realized_today(fills: Sequence[tuple[int, float]], day: int) -> float:
    """Re-deriva el acumulador del día como lo reconstruye el replay del producto.

    ``PaperEngine._realized_pnl_today`` acumula el PnL realizado de cada SELL fill
    y se resetea a 0.0 en el primer evento de un nuevo día UTC (utc_day_index).
    Como los resets ocurren en el cruce de día, tras un replay hasta ``day`` el
    acumulador == Σ pnl de los fills cuyo ``utc_day_index(ts) == day``. Fuente
    autoritativa: los fills persistidos (recovery.py replantea velas y verifica
    contra ellos; no serializa el acumulador).
    """
    return sum(pnl for fill_ts, pnl in fills if utc_day_index(fill_ts) == day)


def run_daily_loss_drill(
    *, base_ms: int | None = None, config: RiskConfig | None = None
) -> tuple[DrillStepResult, ...]:
    """Secuencia completa de daily loss: umbral→BUY rechazado→SELL ok→restart→rollover.

    Refleja el producto: el guard ``daily_loss_exceeded`` (guards.py:15-17) solo
    bloquea exposición nueva (rama BUY, engine.py:81-83); SELL reduce queda
    permitido (engine.py:75-79). El restart conserva la restricción PORQUE el
    replay reconstruye el acumulador del día desde los fills persistidos; el
    rollover UTC resetea la restricción en el primer evento del nuevo día.
    """
    ts = base_ms if base_ms is not None else _now_ms()
    cfg = config or RiskConfig()
    engine = RiskEngine(cfg)
    day = utc_day_index(ts)
    threshold = float(cfg.capital) * float(cfg.max_daily_loss)
    realized = -threshold
    fill_ts = ts + 60_000  # fill SELL (cierre) dentro del mismo día UTC que materializa la pérdida
    persisted_fills: list[tuple[int, float]] = [(fill_ts, realized)]
    steps: list[DrillStepResult] = []
    kill_idle = KillSwitchState()

    breached = daily_loss_exceeded(realized, capital=cfg.capital, config=cfg)
    steps.append(
        DrillStepResult(
            "daily_loss_exceeded",
            breached,
            f"realized={realized} <= -capital*max_daily_loss=-{threshold} → {breached}",
        )
    )

    verdict = _probe(
        engine,
        cfg,
        Action.BUY,
        realized=realized,
        open_positions=0,
        kill_state=kill_idle,
        timestamp_ms=ts,
    )
    ok = not verdict.approved and verdict.reason == "max_daily_loss"
    steps.append(
        DrillStepResult(
            "buy_rejected", ok, f"verdict.reason={verdict.reason} (BUY = nueva exposición)"
        )
    )

    verdict = _probe(
        engine,
        cfg,
        Action.SELL,
        realized=realized,
        open_positions=1,
        kill_state=kill_idle,
        timestamp_ms=ts,
    )
    ok = verdict.approved and verdict.reason == "reduce"
    steps.append(
        DrillStepResult(
            "sell_allowed",
            ok,
            f"verdict.reason={verdict.reason} (SELL reduce no consulta daily loss)",
        )
    )

    derived = _derived_realized_today(persisted_fills, day)
    reconstructed_active = daily_loss_exceeded(derived, capital=cfg.capital, config=cfg)
    verdict = _probe(
        engine,
        cfg,
        Action.BUY,
        realized=derived,
        open_positions=0,
        kill_state=kill_idle,
        timestamp_ms=ts,
    )
    ok = (
        _floats_close(derived, realized)
        and reconstructed_active
        and not verdict.approved
        and verdict.reason == "max_daily_loss"
    )
    steps.append(
        DrillStepResult(
            "restart_persists",
            ok,
            "el producto no serializa el acumulador; el replay re-deriva realized_pnl_today "
            f"desde los fills del día (recovery.py:37-50). derivado={derived} → breached="
            f"{reconstructed_active} → BUY reason={verdict.reason}",
        )
    )

    next_day_ms = (day + 1) * MS_PER_DAY
    rolled = _derived_realized_today(persisted_fills, day + 1)
    cleared = not daily_loss_exceeded(rolled, capital=cfg.capital, config=cfg)
    verdict = _probe(
        engine,
        cfg,
        Action.BUY,
        realized=rolled,
        open_positions=0,
        kill_state=kill_idle,
        timestamp_ms=next_day_ms,
    )
    ok = _floats_close(rolled, 0.0) and cleared and verdict.approved
    steps.append(
        DrillStepResult(
            "utc_rollover_reset",
            ok,
            "primer evento del nuevo día UTC resetea el acumulador (paper_engine.py:141-146, "
            f"utc_day_index={day}→{day + 1}); rolled={rolled} → breached={not cleared} → "
            f"BUY approved={verdict.approved}",
        )
    )
    return tuple(steps)


def sequence_passed(kind: str, steps: Sequence[DrillStepResult]) -> bool:
    """PASS solo si los pasos son exactamente la secuencia canónica y todos pasan."""
    canonical = SEQUENCE_STEPS.get(kind)
    if canonical is None:
        return False
    tokens = [s.step for s in steps]
    return tokens == list(canonical) and all(s.ok for s in steps)


def build_evidence_entry(
    kind: str,
    steps: Sequence[DrillStepResult],
    *,
    artifact: Mapping[str, str],
    at_iso: str,
) -> dict[str, Any]:
    """Entrada de evidencia del drill: type/status/at_iso/steps/artifact (contrato)."""
    return {
        "type": kind,
        "status": "PASS" if sequence_passed(kind, steps) else "FAIL",
        "at_iso": at_iso,
        "steps": [s.step for s in steps],
        "artifact": {key: str(artifact.get(key, "")) for key in ARTIFACT_KEYS},
    }


def load_evidence(path: Path) -> dict[str, Any]:
    """Carga el fichero de evidencia existente; fichero ausente ⇒ {}."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("safeguard evidence must be a JSON object keyed by drill kind")
    return data


def write_evidence_crash_safe(path: Path, evidence: Mapping[str, Any]) -> None:
    """Escritura atómica: tmp + fsync + os.replace + fsync del directorio."""
    serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def _default_application_version() -> str:
    import version  # type: ignore[import-not-found]  # src/version.py (repo/src en sys.path)

    return version.__version__


def _default_strategy_version() -> str:
    from domain.trading.strategy import EmaRsiBaseline

    return EmaRsiBaseline.version


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safeguard_drill.py",
        description="Drill operativo de safeguards (kill switch / daily loss). "
        "Ejecuta la secuencia completa contra los guards reales del dominio y, si "
        "PASS, registra la evidencia de forma crash-safe.",
    )
    parser.add_argument("--kind", choices=("kill_switch", "daily_loss"), required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Ruta del fichero de evidencia "
        f"(default: {DEFAULT_EVIDENCE_RELPATH} relativo al repo)",
    )
    parser.add_argument("--git-commit", default="", help="git_commit del artefacto desplegado")
    parser.add_argument(
        "--application-version",
        default=None,
        help="application_version (default: src/version.py __version__)",
    )
    parser.add_argument(
        "--docker-image-digest", default="", help="docker_image_digest del artefacto desplegado"
    )
    parser.add_argument(
        "--strategy-version",
        default=None,
        help="strategy_version (default: EmaRsiBaseline.version)",
    )
    parser.add_argument(
        "--risk-config-version",
        default=None,
        help="risk_config_version (default: RiskConfig().version)",
    )
    parser.add_argument(
        "--now-ms", type=int, default=None, help="Base de tiempo de la simulación (avanzado/test)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    now_ms = args.now_ms if args.now_ms is not None else _now_ms()
    out_path = (
        args.out.resolve()
        if args.out is not None
        else (_REPO_ROOT / DEFAULT_EVIDENCE_RELPATH).resolve()
    )

    artifact = {
        "git_commit": args.git_commit,
        "application_version": args.application_version
        if args.application_version is not None
        else _default_application_version(),
        "docker_image_digest": args.docker_image_digest,
        "strategy_version": args.strategy_version
        if args.strategy_version is not None
        else _default_strategy_version(),
        "risk_config_version": args.risk_config_version
        if args.risk_config_version is not None
        else RiskConfig().version,
    }
    if not artifact["git_commit"] or not artifact["docker_image_digest"]:
        print(
            "aviso: git_commit / docker_image_digest vacíos ⇒ el matcher del productor "
            "fallará fail-closed al certificar (el operador debe pasarlos en deploy)",
            file=sys.stderr,
        )

    steps = (
        run_kill_switch_drill(base_ms=now_ms)
        if args.kind == "kill_switch"
        else run_daily_loss_drill(base_ms=now_ms)
    )
    for step in steps:
        marker = "PASS" if step.ok else "FAIL"
        print(f"[{marker}] {step.step}: {step.detail}")

    if not sequence_passed(args.kind, steps):
        print(f"safeguard drill '{args.kind}': FAIL", file=sys.stderr)
        return 1

    entry = build_evidence_entry(args.kind, steps, artifact=artifact, at_iso=_iso_utc_ms(now_ms))
    evidence = load_evidence(out_path)
    evidence[args.kind] = entry
    write_evidence_crash_safe(out_path, evidence)
    print(f"safeguard drill '{args.kind}': PASS → evidencia en {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
