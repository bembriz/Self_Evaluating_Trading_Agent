"""E2E Fase 17H: cadena completa del Strategy Lab con baseline-v1 real.

Recorre: dataset → split v1 → DEVELOPMENT/WALK_FORWARD → FrozenDatasetAdapter
→ ExperimentSpec → StrategyArtifactIdentity → KernelIdentity →
LabSessionRunner → ExperimentRun → ExperimentRegistry → walk-forward →
robustness → Promotion. Incluye double-run y ruta de fallo (rechazo
STABLE_NEGATIVE, holdout intacto). Sin holdout, sin MVP-B.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from lab.experiment_spec import ExperimentRun, ExperimentSpec, spec_id
from lab.fingerprints import (
    ImportlibSourceResolver,
    StrategyDefinition,
    strategy_artifact_identity,
)
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.kernel_bundle import make_kernel_identity, real_strategy_contract_source
from lab.promote import (
    ParityEvidence,
    Promotion,
    RobustnessEvidence,
)
from lab.registry import ExperimentRegistry, compare_runs
from lab.robustness import ROBUSTNESS_VARIANTS, summarize_robustness, variant_config
from lab.session_runner import LabSessionRunner
from lab.splits import is_holdout_range
from lab.walk_forward import (
    aggregate_results,
    make_window_result,
    walk_forward_windows,
    window_metrics,
)

REPO = Path(__file__).resolve().parents[2]
APP_SHA = "43ecf5c"
ENGINE_CONFIG = RiskConfig(stop_loss_required=False, version="risk-v1-nostop-mvp-a")
HOLDOUT_FILE = REPO / "holdout" / "v1.state.json"

EXPECTED_WINDOW_NETS = (-3.0835621892615013, -7.022150732859141, -5.968229890314542)
EXPECTED_EXPECTANCY = -0.06353337080013907


class _Chain:
    """Contexto E2E: componentes reales + contadores de acceso al holdout."""

    def __init__(self, root: Path) -> None:
        self.repo = REPO
        self.registry = ExperimentRegistry(root / "registry")
        self.ranges_opened: list[tuple[int, int]] = []
        self.holdout_bytes_before = HOLDOUT_FILE.read_bytes()
        manifest_path = REPO / "docs/datasets/BYBIT_ETHBTC_V001.manifest.json"
        self.manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        resolver = ImportlibSourceResolver()
        defn = StrategyDefinition(
            strategy_id="ema-rsi-baseline",
            strategy_version="baseline-v1",
            kind="deterministic",
            normalized_config={"ema_fast": 20, "ema_slow": 50, "rsi_period": 14, "rsi_exit": 80.0},
            sources=("domain.trading.strategy",),
        )
        self.artifact_identity = strategy_artifact_identity(defn, resolver)
        kernel = make_kernel_identity(resolver, real_strategy_contract_source())
        self.kernel_version = kernel.kernel_bundle_version
        self.kernel_fingerprint = kernel.kernel_fingerprint

    def open_range(self, row_start: int, row_end: int) -> FrozenDatasetAdapter:
        assert not is_holdout_range(row_start, row_end), "E2E never opens holdout"
        self.ranges_opened.append((row_start, row_end))
        return FrozenDatasetAdapter.from_repo(
            self.repo,
            symbol="ETHUSDT",
            timeframe="15m",
            row_start=row_start,
            row_end=row_end,
        )

    def spec_for(self, row_start: int, row_end: int, strategy: dict[str, Any]) -> ExperimentSpec:
        return ExperimentSpec(
            dataset={
                "dataset_id": "BYBIT_ETHBTC_V001",
                "symbol": "ETHUSDT",
                "timeframe": "15m",
                "row_start": row_start,
                "row_end": row_end,
            },
            strategy=strategy,
            risk={"version": ENGINE_CONFIG.version, "capital": ENGINE_CONFIG.capital},
            execution={"model": "runtime-parity", "version": "mvp-a"},
            fees={"version": "bybit-spot-v1"},
            slippage={"version": "conservative-v1"},
            timing_model="mvp-a",
            holdout_protocol="deny-holdout",
            kernel_identity={
                "kernel_bundle_version": self.kernel_version,
                "kernel_fingerprint": self.kernel_fingerprint,
            },
        )

    def baseline_strategy(self) -> dict[str, Any]:
        return {
            "name": "ema-rsi-baseline",
            "version": "baseline-v1",
            "ema_fast": 20,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_exit": 80.0,
            "artifact_identity": self.artifact_identity,
        }

    def run_session(self, row_start: int, row_end: int, linked: str) -> Any:
        adapter = self.open_range(row_start, row_end)
        return LabSessionRunner(
            adapter=adapter,
            strategy=EmaRsiBaseline(),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()

    def register_run(self, linked: str, run_id: str, created_at: str, result: Any) -> ExperimentRun:
        run = ExperimentRun(
            linked,
            run_id,
            created_at,
            APP_SHA,
            "ok",
            result.event_trace_hash,
            result.metrics_hash_value,
        )
        self.registry.register_run(run)
        return run

    def holdout_reads(self) -> int:
        return sum(1 for start, end in self.ranges_opened if start < 103680 and end > 88128)

    def verify_holdout_untouched(self) -> None:
        assert self.holdout_reads() == 0
        assert HOLDOUT_FILE.read_bytes() == self.holdout_bytes_before
        assert json.loads(HOLDOUT_FILE.read_text(encoding="utf-8"))["state"] == "PRISTINE"


def test_e2e_strategy_lab_full_chain(tmp_path: Path) -> None:
    chain = _Chain(tmp_path)

    # 1. Identidad del dataset + split v1.
    assert chain.manifest_sha == "3c008c3ab5299e33beaa61c80ddc927d2f14fc3f96924b5d6db537b2a4e91644"
    split_v1 = json.loads((REPO / "splits" / "v1.json").read_text(encoding="utf-8"))
    assert split_v1["dataset_manifest_sha"] == chain.manifest_sha
    assert split_v1["total_rows"] == 103680
    assert [(s["row_start"], s["row_end"]) for s in split_v1["splits"]] == [
        (0, 62208),
        (62208, 88128),
        (88128, 103680),
    ]

    # 2-5. Spec DEV → adapter → runner → run → registry.
    spec = chain.spec_for(0, 128, chain.baseline_strategy())
    linked = chain.registry.register_spec(spec)
    assert linked == spec_id(spec)
    result = chain.run_session(0, 128, linked)
    run = chain.register_run(linked, "e2e-dev-run", "2026-09-12T07:00:00+00:00", result)
    assert chain.registry.load_run(linked, "e2e-dev-run").run_id == "e2e-dev-run"
    assert run.event_trace_hash is not None and run.metrics_hash is not None

    # 6. Walk-forward completo (3 ventanas reales) + agregado.
    windows = walk_forward_windows(3)
    results = []
    for position, window in enumerate(windows):
        spec = chain.spec_for(window.row_start, window.row_end, chain.baseline_strategy())
        window_linked = chain.registry.register_spec(spec)
        window_result = chain.run_session(window.row_start, window.row_end, window_linked)
        window_run = chain.register_run(
            window_linked,
            f"e2e-wf-{position}",
            f"2026-09-12T07:01:0{position}+00:00",
            window_result,
        )
        results.append(make_window_result(window, window_result, run_id=window_run.run_id))
    for item, expected_net in zip(results, EXPECTED_WINDOW_NETS, strict=True):
        assert item.net_pnl == expected_net
    agg = aggregate_results(tuple(results))
    assert agg["total_windows"] == 3
    assert agg["profitable_windows"] == 0
    assert agg["losing_windows"] == 3
    assert agg["expectancy"] == EXPECTED_EXPECTANCY

    # 7. Robustness representativa (las 7 variantes, slice DEV).
    nets: dict[str, float] = {}
    for variant in ROBUSTNESS_VARIANTS:
        cfg = variant_config(variant)
        adapter = chain.open_range(0, 1024)
        variant_result = LabSessionRunner(
            adapter=adapter,
            strategy=EmaRsiBaseline(cfg),
            engine=PaperEngine(config=ENGINE_CONFIG),
            experiment_spec_id=linked,
        ).run()
        nets[variant.name] = float(window_metrics(variant_result)["net_pnl"])
    summary = summarize_robustness(nets)
    assert summary["variants"] == 7

    # 8. Promoción: parity pasa, robustness rechaza, holdout intacto.
    promotion = Promotion.create(
        tmp_path / "promotions",
        strategy_identity=chain.artifact_identity,
        spec_id_value=linked,
        timestamp="2026-09-12T07:02:00+00:00",
    )
    promotion = promotion.advance_to_parity(
        ParityEvidence(runtime_parity=True, double_run_reproducibility=True),
        timestamp="2026-09-12T07:02:01+00:00",
    )
    assert promotion.state == "PARITY_PASSED"
    try:
        promotion.advance_to_robustness(
            RobustnessEvidence(
                profitable_windows=agg["profitable_windows"],
                losing_windows=agg["losing_windows"],
                expectancy=agg["expectancy"],
                robustness_interpretation="STABLE_NEGATIVE",
                edge_present=False,
                promotable=False,
            ),
            timestamp="2026-09-12T07:02:02+00:00",
        )
        raise AssertionError("baseline must be rejected")
    except Exception as exc:
        assert "NEGATIVE_WALK_FORWARD" in str(exc) or "NO_DEMONSTRATED_EDGE" in str(exc)
    chain.verify_holdout_untouched()


def test_e2e_double_run_reproducibility(tmp_path: Path) -> None:
    chain = _Chain(tmp_path)
    spec = chain.spec_for(0, 128, chain.baseline_strategy())
    linked = chain.registry.register_spec(spec)
    first = chain.run_session(0, 128, linked)
    second = chain.run_session(0, 128, linked)
    run_a = chain.register_run(linked, "e2e-a", "2026-09-12T07:03:00+00:00", first)
    run_b = chain.register_run(linked, "e2e-b", "2026-09-12T07:03:01+00:00", second)
    assert run_a.run_id != run_b.run_id
    report = compare_runs(run_a, run_b)
    assert report.same_spec_id and report.reproducible
    assert report.event_trace_hash_match and report.metrics_hash_match

    def attempt(tag: str) -> str:
        promotion = Promotion.create(
            tmp_path / tag,
            strategy_identity=chain.artifact_identity,
            spec_id_value=linked,
            timestamp="2026-09-12T07:03:02+00:00",
        )
        promotion = promotion.advance_to_parity(
            ParityEvidence(runtime_parity=True, double_run_reproducibility=True),
            timestamp="2026-09-12T07:03:03+00:00",
        )
        try:
            promotion.advance_to_robustness(
                RobustnessEvidence(
                    profitable_windows=0,
                    losing_windows=3,
                    expectancy=EXPECTED_EXPECTANCY,
                    robustness_interpretation="STABLE_NEGATIVE",
                    edge_present=False,
                    promotable=False,
                ),
                timestamp="2026-09-12T07:03:04+00:00",
            )
        except Exception as exc:
            return str(exc)
        raise AssertionError("must reject")

    assert attempt("promo-a") == attempt("promo-b")
    chain.verify_holdout_untouched()
