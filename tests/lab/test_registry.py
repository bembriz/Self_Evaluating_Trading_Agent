"""Tests fase 17E: ExperimentRegistry filesystem + double-run reproducibility.

Sin base de datos, sin promotion logic, sin walk-forward orchestration, sin
holdout. El double-run usa DEVELOPMENT [0, 64) con estrategia y motor reales.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from application.services.paper_engine import PaperEngine
from domain.risk.config import RiskConfig
from domain.trading.strategy import EmaRsiBaseline
from lab.experiment_spec import ExperimentRun, ExperimentSpec, spec_id
from lab.frozen_dataset import FrozenDatasetAdapter
from lab.registry import (
    ExperimentRegistry,
    RunConflictError,
    SpecConflictError,
    compare_runs,
)
from lab.session_runner import LabSessionRunner

REPO = Path(__file__).resolve().parents[2]
APP_SHA = "6411d34"


def _dev_spec(row_end: int = 64) -> ExperimentSpec:
    return ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": 0,
            "row_end": row_end,
        },
        strategy={"name": "ema-rsi-baseline", "version": "baseline-v1"},
        risk={"version": "risk-v1", "capital": 1000.0},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )


def _run(
    linked: str,
    run_id: str,
    trace: str | None = "aa" * 32,
    metrics: str | None = "bb" * 32,
    created_at: str = "2026-09-12T00:00:00+00:00",
) -> ExperimentRun:
    return ExperimentRun(
        experiment_spec_id=linked,
        run_id=run_id,
        created_at=created_at,
        application_git_sha=APP_SHA,
        status="ok",
        event_trace_hash=trace,
        metrics_hash=metrics,
    )


def _session_result(linked: str) -> Any:
    adapter = FrozenDatasetAdapter.from_repo(
        REPO, symbol="ETHUSDT", timeframe="15m", row_start=0, row_end=64
    )
    return LabSessionRunner(
        adapter=adapter,
        strategy=EmaRsiBaseline(),
        engine=PaperEngine(config=RiskConfig()),
        experiment_spec_id=linked,
    ).run()


def test_register_new_spec(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    spec = _dev_spec()
    wanted = spec_id(spec)
    assert registry.register_spec(spec) == wanted
    assert (tmp_path / wanted / "spec.json").is_file()


def test_reregister_same_spec_is_idempotent(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    spec = _dev_spec()
    wanted = registry.register_spec(spec)
    before = (tmp_path / wanted / "spec.json").read_bytes()
    assert registry.register_spec(spec) == wanted
    assert (tmp_path / wanted / "spec.json").read_bytes() == before


def test_conflicting_content_under_same_spec_id_rejected(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    spec = _dev_spec()
    wanted = registry.register_spec(spec)
    payload = json.loads((tmp_path / wanted / "spec.json").read_text(encoding="utf-8"))
    payload["spec"]["dataset"]["row_end"] = 65
    (tmp_path / wanted / "spec.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SpecConflictError):
        registry.register_spec(spec)
    with pytest.raises(SpecConflictError):
        registry.load_spec(wanted)


def test_register_new_run(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    wanted = registry.register_spec(_dev_spec())
    path = registry.register_run(_run(wanted, "run-1"))
    assert path.is_file()
    assert registry.list_runs(wanted) == ("run-1",)


def test_conflicting_content_under_same_run_id_rejected(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    wanted = registry.register_spec(_dev_spec())
    original = _run(wanted, "run-1")
    registry.register_run(original)
    path = tmp_path / wanted / "runs" / "run-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["run"]["created_at"] = "2026-09-12T00:00:01+00:00"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunConflictError):
        registry.register_run(original)
    payload["run"]["run_id"] = "run-2"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunConflictError):
        registry.load_run(wanted, "run-1")


def test_registry_survives_filesystem_reload(tmp_path: Path) -> None:
    wanted = ExperimentRegistry(tmp_path).register_spec(_dev_spec())
    ExperimentRegistry(tmp_path).register_run(_run(wanted, "run-1"))
    fresh = ExperimentRegistry(tmp_path)
    assert spec_id(fresh.load_spec(wanted)) == wanted
    assert fresh.load_run(wanted, "run-1").run_id == "run-1"
    assert fresh.list_runs(wanted) == ("run-1",)


def test_run_requires_registered_spec(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="spec no registrado"):
        ExperimentRegistry(tmp_path).register_run(_run("ab" * 32, "run-x"))


def test_unknown_ids_and_bad_ids_fail_closed(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    with pytest.raises(FileNotFoundError):
        registry.load_spec("ab" * 32)
    with pytest.raises(ValueError, match="spec_id inválido"):
        registry.load_spec("not-a-hash")
    with pytest.raises(FileNotFoundError):
        registry.load_run("ab" * 32, "run-x")
    with pytest.raises(ValueError, match="run_id inválido"):
        registry.load_run("ab" * 32, "../escape")
    assert registry.list_runs("ab" * 32) == ()


def test_double_run_reproducibility() -> None:
    spec = _dev_spec()
    linked = spec_id(spec)
    first = _session_result(linked)
    second = _session_result(linked)
    assert first.experiment_spec_id == second.experiment_spec_id == linked
    assert first.event_trace_hash == second.event_trace_hash
    assert first.metrics_hash_value == second.metrics_hash_value


def test_double_run_registered_with_different_run_ids(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    linked = registry.register_spec(_dev_spec())
    first = _session_result(linked)
    second = _session_result(linked)
    run_a = _run(
        linked,
        "17e-double-a",
        first.event_trace_hash,
        first.metrics_hash_value,
        "2026-09-12T00:00:00+00:00",
    )
    run_b = _run(
        linked,
        "17e-double-b",
        second.event_trace_hash,
        second.metrics_hash_value,
        "2026-09-12T00:00:01+00:00",
    )
    registry.register_run(run_a)
    registry.register_run(run_b)
    assert run_a.run_id != run_b.run_id
    report = compare_runs(
        registry.load_run(linked, "17e-double-a"), registry.load_run(linked, "17e-double-b")
    )
    assert report.same_spec_id is True
    assert report.event_trace_hash_match is True
    assert report.metrics_hash_match is True
    assert report.reproducible is True


def test_compare_runs_not_reproducible_when_diverging() -> None:
    linked = spec_id(_dev_spec())
    other = spec_id(_dev_spec(row_end=65))
    assert compare_runs(_run(linked, "a"), _run(other, "b")).reproducible is False
    assert compare_runs(_run(linked, "a"), _run(other, "b")).same_spec_id is False
    assert (
        compare_runs(_run(linked, "a", trace=None), _run(linked, "b")).event_trace_hash_match
        is False
    )
    assert (
        compare_runs(_run(linked, "a"), _run(linked, "b", metrics=None)).metrics_hash_match is False
    )


def test_semantic_change_yields_different_spec_id() -> None:
    assert spec_id(_dev_spec()) != spec_id(_dev_spec(row_end=65))


def test_reregister_same_run_is_idempotent(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    wanted = registry.register_spec(_dev_spec())
    run = _run(wanted, "run-1")
    first = registry.register_run(run)
    assert registry.register_run(run) == first


def test_spec_with_nested_sequences_round_trips(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path)
    spec = ExperimentSpec(
        dataset={
            "dataset_id": "BYBIT_ETHBTC_V001",
            "symbol": "ETHUSDT",
            "timeframe": "15m",
            "row_start": 0,
            "row_end": 64,
            "tags": ("dev", "smoke"),
        },
        strategy={"name": "ema-rsi-baseline", "version": "baseline-v1"},
        risk={"version": "risk-v1", "capital": 1000.0},
        execution={"model": "runtime-parity", "version": "mvp-a"},
        fees={"version": "bybit-spot-v1"},
        slippage={"version": "conservative-v1"},
        timing_model="mvp-a",
        holdout_protocol="deny-holdout",
        kernel_identity={"kernel_bundle_version": 1, "kernel_fingerprint": "00" * 32},
    )
    wanted = registry.register_spec(spec)
    loaded = registry.load_spec(wanted)
    assert spec_id(loaded) == wanted
    assert list(loaded.dataset["tags"]) == ["dev", "smoke"]


def test_final_holdout_blocked() -> None:
    with pytest.raises(ValueError, match="FINAL_HOLDOUT"):
        FrozenDatasetAdapter.from_repo(
            REPO, symbol="ETHUSDT", timeframe="15m", row_start=88128, row_end=88129
        )
