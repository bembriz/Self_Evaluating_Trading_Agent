"""Tests fase 17A: ExperimentSpec/Run, canonicalización e identidad determinista.

TDD RED: estos tests definen el contrato antes de la implementación.
Convenciones: dataclasses frozen del dominio, sin persistencia, sin red.
"""

from __future__ import annotations

import copy
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum, IntEnum, StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest

from lab.experiment_spec import (
    ALLOWED_EXECUTION_MODELS,
    ExperimentRun,
    ExperimentSpec,
    canonical_json,
    event_trace_hash,
    metrics_hash,
    sha256_hex,
    spec_id,
)


class Color(Enum):
    RED = "red"


class Shade(StrEnum):
    DARK = "dark"


class Level(IntEnum):
    HIGH = 3


def _base_kwargs() -> dict[str, Any]:
    return {
        "dataset": {
            "id": "BYBIT_ETHBTC_V001",
            "manifest_sha": "ab" * 32,
            "slice": {
                "kind": "development",
                "rows": [0, 86400],
                "slice_sha": "cd" * 32,
                "split_manifest": "splits/v1",
            },
        },
        "strategy": {
            "identity": "ema-rsi-baseline",
            "version": "baseline-v1",
            "config": {"ema_fast": 20, "rsi_exit": 80.0},
            "implementation_fingerprint": "ef" * 32,
        },
        "risk": {"version": "risk-v1", "config_sha": "01" * 32},
        "execution": {"model": "runtime-parity", "version": "v1", "parameters": {}},
        "fees": {
            "model": "FeeModel",
            "version": "bybit-spot-v1",
            "params": {"taker_bps": 10.0},
        },
        "slippage": {
            "model": "SlippageModel",
            "version": "conservative-v1",
            "params": {"bps": 2.0},
        },
        "timing_model": "same-bar-close-v1",
        "seed": None,
        "walk_forward": None,
        "holdout_protocol": "holdout-v1",
        "kernel_identity": {"placeholder": "17B"},
    }


def _reversed(obj: object) -> object:
    if isinstance(obj, dict):
        return {k: _reversed(obj[k]) for k in reversed(list(obj.keys()))}
    if isinstance(obj, list):
        return [_reversed(v) for v in obj]
    return obj


# ---------------------------------------------------------------- SpecId basics


def test_same_semantic_inputs_same_spec_id() -> None:
    assert spec_id(ExperimentSpec(**_base_kwargs())) == spec_id(ExperimentSpec(**_base_kwargs()))


def test_dict_key_ordering_irrelevant() -> None:
    assert spec_id(ExperimentSpec(**_base_kwargs())) == spec_id(
        ExperimentSpec(**cast(dict[str, Any], _reversed(_base_kwargs())))
    )


def test_nested_key_ordering_irrelevant() -> None:
    kwargs = _base_kwargs()
    kwargs["strategy"] = _reversed(kwargs["strategy"])
    kwargs["dataset"]["slice"] = _reversed(kwargs["dataset"]["slice"])
    assert spec_id(ExperimentSpec(**kwargs)) == spec_id(ExperimentSpec(**_base_kwargs()))


def _mutate(base: dict[str, Any], dotted: str, value: object) -> dict[str, Any]:
    out: dict[str, Any] = copy.deepcopy(base)
    node: dict[str, Any] = out
    *path, last = dotted.split(".")
    for key in path:
        node = cast(dict[str, Any], node[key])
    node[last] = value
    return out


@pytest.mark.parametrize(
    ("dotted", "value"),
    [
        ("dataset.id", "OTHER_DATASET"),
        ("dataset.slice.rows", [0, 100]),
        ("dataset.slice.kind", "walkforward"),
        ("strategy.identity", "other-strategy"),
        ("strategy.version", "baseline-v2"),
        ("strategy.config", {"ema_fast": 21}),
        ("strategy.implementation_fingerprint", "00" * 32),
        ("risk.version", "risk-v2"),
        ("risk.config_sha", "ff" * 32),
        ("execution.model", "fast-research"),
        ("execution.version", "v2"),
        ("execution.parameters", {"latency_ms": 5}),
        ("fees.version", "other-fees"),
        ("fees.params", {"taker_bps": 25.0}),
        ("slippage.version", "other-slip"),
        ("slippage.params", {"bps": 10.0}),
        ("timing_model", "next-open-v1"),
        ("seed", "seed-1"),
        ("walk_forward", {"protocol": "wf-v1", "window": [0, 100]}),
        ("holdout_protocol", "holdout-v2"),
        ("kernel_identity", {"placeholder": "17B-changed"}),
    ],
)
def test_semantic_field_change_changes_spec_id(dotted: str, value: object) -> None:
    mutated = _mutate(_base_kwargs(), dotted, value)
    assert spec_id(ExperimentSpec(**mutated)) != spec_id(ExperimentSpec(**_base_kwargs()))


# ------------------------------------------------- deep immutability


def test_top_level_mapping_mutation_rejected() -> None:
    spec = ExperimentSpec(**_base_kwargs())
    holder: Any = spec.dataset
    with pytest.raises(TypeError):
        holder["id"] = "OTHER"


def test_deep_nested_mapping_mutation_rejected() -> None:
    spec = ExperimentSpec(**_base_kwargs())
    nested: Any = spec.dataset["slice"]
    with pytest.raises(TypeError):
        nested["kind"] = "walkforward"


def test_slice_list_mutation_rejected() -> None:
    spec = ExperimentSpec(**_base_kwargs())
    rows: Any = spec.dataset["slice"]["rows"]
    with pytest.raises(TypeError):
        rows[0] = 999
    with pytest.raises(AttributeError):
        rows.append(999)


def test_caller_mutation_does_not_alter_spec() -> None:
    kwargs = _base_kwargs()
    spec = ExperimentSpec(**kwargs)
    before = spec_id(spec)
    kwargs["dataset"]["id"] = "OTHER"
    kwargs["dataset"]["slice"]["rows"].append(999)
    kwargs["dataset"]["slice"]["kind"] = "walkforward"
    kwargs["strategy"]["config"]["ema_fast"] = 999
    assert spec_id(spec) == before
    assert spec.dataset["id"] == "BYBIT_ETHBTC_V001"
    assert list(spec.dataset["slice"]["rows"]) == [0, 86400]


def test_spec_id_stable_across_mutation_attempts() -> None:
    spec = ExperimentSpec(**_base_kwargs())
    before = spec_id(spec)
    dataset: Any = spec.dataset
    strategy: Any = spec.strategy
    rows: Any = spec.dataset["slice"]["rows"]

    def _set_dataset() -> None:
        dataset["id"] = "X"

    def _set_strategy() -> None:
        strategy["version"] = "v9"

    def _set_row() -> None:
        rows[0] = 1

    for attempt in (_set_dataset, _set_strategy, _set_row):
        with pytest.raises(TypeError):
            attempt()
    assert spec_id(spec) == before


def test_frozen_containers_have_expected_types() -> None:
    spec = ExperimentSpec(**_base_kwargs())
    assert isinstance(spec.dataset, MappingProxyType)
    assert isinstance(spec.dataset["slice"], MappingProxyType)
    assert isinstance(spec.dataset["slice"]["rows"], tuple)


# ------------------------------------------------- Run/provenance separation


def _run(**overrides: object) -> ExperimentRun:
    base: dict[str, Any] = {
        "experiment_spec_id": "aa" * 32,
        "run_id": "r-01",
        "created_at": "2026-09-11T00:00:00+00:00",
        "application_git_sha": "abc123",
        "status": "ok",
        "event_trace_hash": "bb" * 32,
        "metrics_hash": "cc" * 32,
    }
    base.update(overrides)
    return ExperimentRun(**base)


def test_created_at_does_not_alter_spec_id() -> None:
    sid = spec_id(ExperimentSpec(**_base_kwargs()))
    assert (
        _run().experiment_spec_id == _run(created_at="2027-01-01T00:00:00+00:00").experiment_spec_id
    )
    # End-to-end: identical semantics keep experimental identity across runs.
    assert sid == spec_id(ExperimentSpec(**_base_kwargs()))


def test_run_id_does_not_alter_spec_id() -> None:
    assert _run(run_id="r-01").experiment_spec_id == _run(run_id="r-02").experiment_spec_id


def test_result_hashes_do_not_alter_spec_id() -> None:
    assert (
        _run(event_trace_hash="bb" * 32).experiment_spec_id
        == _run(event_trace_hash="dd" * 32).experiment_spec_id
    )
    assert (
        _run(metrics_hash="cc" * 32).experiment_spec_id
        == _run(metrics_hash="ee" * 32).experiment_spec_id
    )


def test_application_git_sha_does_not_alter_spec_id() -> None:
    sid = spec_id(ExperimentSpec(**_base_kwargs()))
    assert (
        _run(application_git_sha="abc123").experiment_spec_id
        == _run(application_git_sha="def456").experiment_spec_id
    )
    # Provenance criterion: identical semantics + different code revision
    # still resolve to the same experimental identity.
    assert sid == spec_id(ExperimentSpec(**_base_kwargs()))


def test_runs_share_real_spec_identity_across_provenance() -> None:
    sid = spec_id(ExperimentSpec(**_base_kwargs()))
    run_a = ExperimentRun(
        experiment_spec_id=sid,
        run_id="r-a",
        created_at="2026-09-11T00:00:00+00:00",
        application_git_sha="aaa111",
        status="ok",
        event_trace_hash="bb" * 32,
        metrics_hash="cc" * 32,
    )
    run_b = ExperimentRun(
        experiment_spec_id=sid,
        run_id="r-b",
        created_at="2026-09-12T00:00:00+00:00",
        application_git_sha="bbb222",
        status="ok",
        event_trace_hash="dd" * 32,
        metrics_hash="ee" * 32,
    )
    # Provenance differs entirely, yet experimental identity is one and the same.
    assert run_a.experiment_spec_id == sid
    assert run_b.experiment_spec_id == sid
    assert run_a.application_git_sha != run_b.application_git_sha
    assert run_a.run_id != run_b.run_id


# ---------------------------------------------------------------- canonical


def test_canonical_primitives_and_separators() -> None:
    assert canonical_json({"b": 1, "a": [1, 2.5, "x", True, None]}) == (
        '{"a":[1,2.5,"x",true,null],"b":1}'
    )


def test_canonical_tuple_is_list_and_documented() -> None:
    assert canonical_json((1, 2)) == "[1,2]"


def test_canonical_unicode_stable() -> None:
    assert canonical_json({"k": "caña-ETH"}) == canonical_json({"k": "caña-ETH"})
    assert "\\u00f1" in canonical_json({"k": "ñ"})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_canonical_rejects_nonfinite_float(bad: float) -> None:
    with pytest.raises(ValueError, match="[Ff]inite|nan|inf"):
        canonical_json({"v": bad})


def test_canonical_rejects_decimal() -> None:
    with pytest.raises(TypeError, match="[Dd]ecimal"):
        canonical_json({"v": Decimal("1.1")})


def test_canonical_rejects_datetime() -> None:
    with pytest.raises(TypeError, match="datetime|ISO"):
        canonical_json({"v": datetime(2026, 1, 1, tzinfo=UTC)})


def test_canonical_rejects_enum() -> None:
    with pytest.raises(TypeError, match="[Ee]num"):
        canonical_json({"v": Color.RED})


def test_canonical_rejects_strenum_before_str() -> None:
    # StrEnum IS a str: must be rejected before str acceptance (fail-closed).
    assert isinstance(Shade.DARK, str)
    with pytest.raises(TypeError, match="[Ee]num"):
        canonical_json({"v": Shade.DARK})


def test_canonical_rejects_intenum_before_int() -> None:
    # IntEnum IS an int: must be rejected before int acceptance (fail-closed).
    assert isinstance(Level.HIGH, int)
    with pytest.raises(TypeError, match="[Ee]num"):
        canonical_json({"v": Level.HIGH})


def test_canonical_rejects_path() -> None:
    with pytest.raises(TypeError, match="[Pp]ath"):
        canonical_json({"v": Path("a/b")})


def test_canonical_rejects_bytes() -> None:
    with pytest.raises(TypeError, match="bytes"):
        canonical_json({"v": b"ab"})


@pytest.mark.parametrize("bad", [{1, 2}, frozenset({1})])
def test_canonical_rejects_sets(bad: object) -> None:
    with pytest.raises(TypeError, match="[Ss]et"):
        canonical_json({"v": bad})


def test_canonical_rejects_non_string_keys() -> None:
    bad: dict[Any, Any] = {1: "x"}
    with pytest.raises(TypeError, match="[Kk]ey"):
        canonical_json(bad)


def test_canonical_rejects_arbitrary_objects() -> None:
    class Opaque:
        pass

    with pytest.raises(TypeError, match="[Uu]nsupported|object"):
        canonical_json({"v": Opaque()})


def test_canonical_distinguishes_signed_zero_and_int_float() -> None:
    assert canonical_json(0.0) != canonical_json(-0.0)
    assert canonical_json(1) != canonical_json(1.0)


# ---------------------------------------------------------------- trace/metric


def test_event_trace_hash_deterministic() -> None:
    events = [{"ts": 1, "action": "BUY", "exec": 100.02}]
    assert event_trace_hash(events) == event_trace_hash(events)


def test_metrics_hash_deterministic() -> None:
    metrics = {"net_pnl": -43.25, "trades": 1055}
    assert metrics_hash(metrics) == metrics_hash(metrics)


def test_one_byte_trace_change_changes_hash() -> None:
    a = [{"ts": 1, "action": "BUY"}]
    b = [{"ts": 1, "action": "BUY "}]
    assert event_trace_hash(a) != event_trace_hash(b)


def test_one_metric_change_changes_hash() -> None:
    assert metrics_hash({"net_pnl": 1.0}) != metrics_hash({"net_pnl": 1.5})


# ---------------------------------------------------------------- modes/runs


def test_allowed_execution_models() -> None:
    assert frozenset({"fast-research", "runtime-parity"}) == ALLOWED_EXECUTION_MODELS


def test_unknown_execution_model_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["execution"] = {"model": "market-realism", "version": "v1", "parameters": {}}
    with pytest.raises(ValueError, match="[Mm]odel"):
        ExperimentSpec(**kwargs)


def test_unknown_model_name_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["execution"] = {"model": "nope", "version": "v1", "parameters": {}}
    with pytest.raises(ValueError, match="[Mm]odel"):
        ExperimentSpec(**kwargs)


def test_execution_missing_version_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["execution"] = {"model": "runtime-parity"}
    with pytest.raises(ValueError, match="[Vv]ersion"):
        ExperimentSpec(**kwargs)


def test_execution_empty_version_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["execution"] = {"model": "runtime-parity", "version": ""}
    with pytest.raises(ValueError, match="[Vv]ersion"):
        ExperimentSpec(**kwargs)


def test_execution_non_mapping_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["execution"] = ["runtime-parity"]
    with pytest.raises(TypeError, match="mapping"):
        ExperimentSpec(**kwargs)


def test_non_mapping_section_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["dataset"] = ["BYBIT_ETHBTC_V001"]
    with pytest.raises(TypeError, match="mapping"):
        ExperimentSpec(**kwargs)


def test_non_string_seed_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["seed"] = 42
    with pytest.raises(TypeError, match="seed"):
        ExperimentSpec(**kwargs)


def test_empty_timing_model_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["timing_model"] = ""
    with pytest.raises(ValueError, match="timing_model"):
        ExperimentSpec(**kwargs)


def test_empty_holdout_protocol_fail_closed() -> None:
    kwargs = _base_kwargs()
    kwargs["holdout_protocol"] = ""
    with pytest.raises(ValueError, match="holdout_protocol"):
        ExperimentSpec(**kwargs)


def test_valid_run_accepted() -> None:
    run = _run()
    assert run.status == "ok"
    assert len(run.experiment_spec_id) == 64


@pytest.mark.parametrize("bad", ["xyz", "AA" * 32, "aa" * 31, "", "aa" * 32 + "a"])
def test_run_rejects_bad_spec_id_format(bad: str) -> None:
    with pytest.raises(ValueError, match="[Ss]pec"):
        _run(experiment_spec_id=bad)


@pytest.mark.parametrize("bad", ["ok ", "DONE", "", "running"])
def test_run_rejects_bad_status(bad: str) -> None:
    with pytest.raises(ValueError, match="[Ss]tatus"):
        _run(status=bad)


def test_run_rejects_bad_hash_format() -> None:
    with pytest.raises(ValueError, match="[Hh]ash"):
        _run(event_trace_hash="zz")
    with pytest.raises(ValueError, match="[Hh]ash"):
        _run(metrics_hash="cc" * 31)


def test_run_allows_missing_result_hashes() -> None:
    run = _run(event_trace_hash=None, metrics_hash=None)
    assert run.event_trace_hash is None


def test_run_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError, match="[Rr]un"):
        _run(run_id="   ")


def test_run_rejects_bad_created_at() -> None:
    with pytest.raises(ValueError, match="created_at|ISO"):
        _run(created_at="not-a-date")


def test_run_rejects_empty_git_sha() -> None:
    with pytest.raises(ValueError, match="git_sha|empty"):
        _run(application_git_sha="")


# ---------------------------------------------------------------- goldens

GOLDEN_CANONICAL = '{"a":[1,2.5,"x",true,null],"b":1}'
GOLDEN_EVENT_TRACE = [{"ts": 1, "action": "BUY", "exec": 100.02}]
GOLDEN_METRICS = {"net_pnl": -43.25, "trades": 1055}


def test_golden_canonical_vectors() -> None:
    # Expected hashes below are hardcoded after independent sha256sum verification.
    assert canonical_json({"b": 1, "a": [1, 2.5, "x", True, None]}) == GOLDEN_CANONICAL
    assert sha256_hex(GOLDEN_CANONICAL.encode("utf-8")) == (
        "b4643e9de89170ba89413d223e33266979cbb8ce6fe29dec9b18fd4bd49949ad"
    )
    assert event_trace_hash(GOLDEN_EVENT_TRACE) == (
        "783829de9e2d974880d89620451fb737ff5d0d380c60592dc0efdbca40a04879"
    )
    assert metrics_hash(GOLDEN_METRICS) == (
        "03dd7b93a3812a80b625df9c5de006ac35e091d841a35b35d48b60c867520160"
    )


def test_golden_spec_id_vector() -> None:
    assert spec_id(ExperimentSpec(**_base_kwargs())) == (
        "f5e4a00f70d5b5af88c53e29366362427f51cbfc1c56de0b678229c3c99b0f89"
    )


def test_second_process_reproducibility() -> None:
    code = (
        "import sys; sys.path.insert(0,'SRCROOT');"
        "from lab.experiment_spec import ExperimentSpec, spec_id;"
        f"spec={_base_kwargs()!r};"
        "print(spec_id(ExperimentSpec(**spec)))"
    )
    root = str(Path(__file__).resolve().parents[2] / "src")
    proc = subprocess.run(
        [sys.executable, "-c", code.replace("SRCROOT", root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == spec_id(ExperimentSpec(**_base_kwargs()))


def test_sha256_hex_format() -> None:
    digest = sha256_hex(b"abc")
    assert digest == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
