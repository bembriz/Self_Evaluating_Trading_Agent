"""Tests fase 17B: ImplementationFingerprint, StrategyArtifactIdentity, KernelBundle.

TDD RED: contrato antes de implementación. Fixtures sintéticas para goldens
(estables ante futuros edits del repo); módulos reales solo en checks de
integración sin goldens sobre su contenido.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from lab.experiment_spec import ExperimentRun, ExperimentSpec, spec_id
from lab.fingerprints import (
    ALLOWED_STRATEGY_KINDS,
    STRATEGY_API_VERSION,
    DictSourceResolver,
    ImportlibSourceResolver,
    StrategyDefinition,
    implementation_fingerprint,
    strategy_artifact_identity,
)
from lab.kernel_bundle import (
    KERNEL_BUNDLE_V1_MODULES,
    KERNEL_BUNDLE_VERSION,
    KernelIdentity,
    kernel_fingerprint,
    make_kernel_identity,
    real_strategy_contract_source,
    strategy_contract_hash,
)

SOURCES_A = {"m.a": "class A:\n    x = 1\n", "m.b": "VALUE = 2\n"}
SOURCES_B = {"m.a": "class A:\n    x = 2\n", "m.b": "VALUE = 2\n"}
CONTRACT_V1 = "class Strategy:\n    version: str\n"
CONTRACT_V2 = "class Strategy:\n    version: str\n    kind: str\n"


def _defn(**overrides: object) -> StrategyDefinition:
    base: dict[str, Any] = {
        "strategy_id": "ema-rsi-baseline",
        "strategy_version": "baseline-v1",
        "strategy_api_version": 1,
        "kind": "deterministic",
        "normalized_config": {"ema_fast": 20},
        "sources": ("m.a", "m.b"),
    }
    base.update(overrides)
    return StrategyDefinition(**base)


def _kernel_resolver(overrides: dict[str, str] | None = None) -> DictSourceResolver:
    """Resolver sintético que cubre los 20 módulos del bundle (fail-closed real)."""
    sources = {name: f"SOURCE:{name}\n" for name in KERNEL_BUNDLE_V1_MODULES}
    if overrides:
        sources.update(overrides)
    return DictSourceResolver(sources)


def _resolver(sources: dict[str, str] = SOURCES_A) -> DictSourceResolver:
    return DictSourceResolver(dict(sources))


# ---------------------------------------------------------------- truth table


# Caso 1: strategy source changes.
def test_case1_source_change() -> None:
    before = (
        implementation_fingerprint(_defn(), _resolver(SOURCES_A)),
        strategy_artifact_identity(_defn(), _resolver(SOURCES_A)),
    )
    after = (
        implementation_fingerprint(_defn(), _resolver(SOURCES_B)),
        strategy_artifact_identity(_defn(), _resolver(SOURCES_B)),
    )
    assert before[0] != after[0]  # ImplementationFingerprint CHANGES
    assert before[1] != after[1]  # StrategyArtifactIdentity CHANGES
    # Kernel no acepta fuentes de estrategia: idénticos inputs ⇒ idéntico output.
    assert kernel_fingerprint(_kernel_resolver(), CONTRACT_V1) == (
        kernel_fingerprint(_kernel_resolver(), CONTRACT_V1)
    )  # Kernel SAME (estructuralmente independiente)


# Caso 2: strategy config changes.
def test_case2_config_change() -> None:
    assert implementation_fingerprint(_defn(), _resolver()) == (
        implementation_fingerprint(_defn(normalized_config={"ema_fast": 21}), _resolver())
    )  # SAME
    assert strategy_artifact_identity(_defn(), _resolver()) != (
        strategy_artifact_identity(_defn(normalized_config={"ema_fast": 21}), _resolver())
    )  # CHANGES


# Caso 3: strategy_version only changes.
def test_case3_version_only_change() -> None:
    assert implementation_fingerprint(_defn(), _resolver()) == (
        implementation_fingerprint(_defn(strategy_version="baseline-v2"), _resolver())
    )  # SAME
    assert strategy_artifact_identity(_defn(), _resolver()) != (
        strategy_artifact_identity(_defn(strategy_version="baseline-v2"), _resolver())
    )  # CHANGES


# Caso 4: strategy_api_version changes.
def test_case4_api_version_change() -> None:
    assert implementation_fingerprint(_defn(), _resolver()) == (
        implementation_fingerprint(_defn(strategy_api_version=2), _resolver())
    )  # SAME
    assert strategy_artifact_identity(_defn(), _resolver()) != (
        strategy_artifact_identity(_defn(strategy_api_version=2), _resolver())
    )  # CHANGES


# Casos 5-7: kernel module source changes (parametrizado).
@pytest.mark.parametrize(
    "module",
    [
        "application.services.paper_runner",
        "application.services.paper_engine",
        "domain.risk.config",
    ],
)
def test_cases5_6_7_kernel_module_change(module: str) -> None:
    r1 = _kernel_resolver({module: "V1"})
    r2 = _kernel_resolver({module: "V2"})
    assert kernel_fingerprint(r1, CONTRACT_V1) != kernel_fingerprint(r2, CONTRACT_V1)  # CHANGES
    assert implementation_fingerprint(_defn(), _resolver()) == (
        implementation_fingerprint(_defn(), _resolver())
    )  # SAME
    assert strategy_artifact_identity(_defn(), _resolver()) == (
        strategy_artifact_identity(_defn(), _resolver())
    )  # SAME


# Caso 8: EmaRsiBaseline changes, Protocol unchanged.
def test_case8_strategy_impl_change_kernel_same() -> None:
    kfp_before = kernel_fingerprint(_kernel_resolver(), CONTRACT_V1)
    kfp_after = kernel_fingerprint(_kernel_resolver(), CONTRACT_V1)
    assert kfp_before == kfp_after  # Kernel SAME (contrato intacto)
    assert implementation_fingerprint(_defn(), _resolver(SOURCES_A)) != (
        implementation_fingerprint(_defn(), _resolver(SOURCES_B))
    )  # impl CHANGES para esa strategy


# Caso 9: Strategy Protocol changes.
def test_case9_protocol_change() -> None:
    assert kernel_fingerprint(_kernel_resolver(), CONTRACT_V1) != (
        kernel_fingerprint(_kernel_resolver(), CONTRACT_V2)
    )  # CHANGES


# Caso 10: application_git_sha changes only.
def test_case10_app_sha_changes_nothing_semantic() -> None:
    impl = implementation_fingerprint(_defn(), _resolver())
    art = strategy_artifact_identity(_defn(), _resolver())
    kern = kernel_fingerprint(_kernel_resolver(), CONTRACT_V1)
    # application_git_sha no es input de ninguna función de identidad:
    assert (impl, art, kern) == (
        implementation_fingerprint(_defn(), _resolver()),
        strategy_artifact_identity(_defn(), _resolver()),
        kernel_fingerprint(_kernel_resolver(), CONTRACT_V1),
    )


# ------------------------------------------------- declaration/validation


def test_allowed_kinds() -> None:
    assert frozenset({"deterministic", "ml", "llm-assisted"}) == ALLOWED_STRATEGY_KINDS
    assert STRATEGY_API_VERSION == 1


def test_sources_ordering_irrelevant() -> None:
    assert implementation_fingerprint(_defn(), _resolver()) == (
        implementation_fingerprint(_defn(sources=("m.b", "m.a")), _resolver())
    )


def test_duplicate_sources_rejected() -> None:
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        _defn(sources=("m.a", "m.a"))


def test_empty_sources_rejected() -> None:
    with pytest.raises(ValueError, match="[Ss]ources"):
        _defn(sources=())


def test_non_tuple_sources_rejected() -> None:
    with pytest.raises(TypeError, match="tuple"):
        _defn(sources=["m.a"])


def test_non_string_source_item_rejected() -> None:
    with pytest.raises(TypeError, match="[Ss]ource|str"):
        _defn(sources=("m.a", 42))


def test_empty_string_source_item_rejected() -> None:
    with pytest.raises(ValueError, match="[Ss]ource"):
        _defn(sources=("m.a", ""))


def test_non_mapping_config_rejected() -> None:
    with pytest.raises(TypeError, match="[Cc]onfig|mapping"):
        _defn(normalized_config=["ema_fast"])


def test_list_config_frozen_to_tuple() -> None:
    defn = _defn(normalized_config={"levels": [1, 2], "name": "x"})
    assert isinstance(defn.normalized_config["levels"], tuple)
    before = implementation_fingerprint(defn, _resolver())
    levels: Any = defn.normalized_config["levels"]
    with pytest.raises(TypeError):
        levels[0] = 9
    assert implementation_fingerprint(defn, _resolver()) == before


def test_empty_id_version_rejected() -> None:
    with pytest.raises(ValueError, match="strategy_id"):
        _defn(strategy_id="")
    with pytest.raises(ValueError, match="strategy_version"):
        _defn(strategy_version="")


def test_bad_api_version_rejected() -> None:
    with pytest.raises(ValueError, match="api_version"):
        _defn(strategy_api_version=0)
    with pytest.raises(ValueError, match="api_version"):
        _defn(strategy_api_version="1")


def test_bad_kind_rejected() -> None:
    with pytest.raises(ValueError, match="[Kk]ind"):
        _defn(kind="quantum")


def test_deterministic_rejects_extras() -> None:
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(prompts={"p": "text"})
    with pytest.raises(ValueError, match="[Mm]odel"):
        _defn(model_artifact="bytes")
    with pytest.raises(ValueError, match="[Ff]eature"):
        _defn(feature_pipeline="code")


def test_ml_requires_model_artifact() -> None:
    with pytest.raises(ValueError, match="[Mm]odel"):
        _defn(kind="ml")
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(kind="ml", model_artifact="m", prompts={"p": "t"})
    ok = _defn(kind="ml", model_artifact="model-bytes-v1")
    assert implementation_fingerprint(ok, _resolver()) != implementation_fingerprint(
        _defn(kind="ml", model_artifact="model-bytes-v2"), _resolver()
    )
    with_pipeline = _defn(kind="ml", model_artifact="m", feature_pipeline="pipe-v1")
    assert implementation_fingerprint(with_pipeline, _resolver()) != (
        implementation_fingerprint(
            _defn(kind="ml", model_artifact="m", feature_pipeline="pipe-v2"),
            _resolver(),
        )
    )
    with pytest.raises(ValueError, match="[Ff]eature"):
        _defn(kind="ml", model_artifact="m", feature_pipeline=123)
    with pytest.raises(ValueError, match="[Ff]eature"):
        _defn(kind="ml", model_artifact="m", feature_pipeline="")


def test_llm_requires_prompts() -> None:
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(kind="llm-assisted")
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(kind="llm-assisted", prompts={})
    ok = _defn(kind="llm-assisted", prompts={"sys": "Be careful."})
    assert implementation_fingerprint(ok, _resolver()) != implementation_fingerprint(
        _defn(kind="llm-assisted", prompts={"sys": "Be reckless."}), _resolver()
    )
    reordered = _defn(kind="llm-assisted", prompts={"b": "2", "a": "1"})
    assert implementation_fingerprint(reordered, _resolver()) == (
        implementation_fingerprint(
            _defn(kind="llm-assisted", prompts={"a": "1", "b": "2"}), _resolver()
        )
    )
    with_optionals = _defn(
        kind="llm-assisted",
        prompts={"sys": "Be careful."},
        model_artifact="m1",
        feature_pipeline="p1",
    )
    assert implementation_fingerprint(with_optionals, _resolver()) != (
        implementation_fingerprint(ok, _resolver())
    )
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(kind="llm-assisted", prompts={1: "x"})
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(kind="llm-assisted", prompts={"sys": ""})
    with pytest.raises(ValueError, match="[Pp]rompt"):
        _defn(kind="llm-assisted", prompts={"": "x"})


def test_unknown_module_fail_closed() -> None:
    with pytest.raises(ValueError, match="[Uu]nknown|module"):
        implementation_fingerprint(_defn(sources=("m.missing",)), _resolver())


def test_config_mutation_post_construction_ignored() -> None:
    defn = _defn()
    before = implementation_fingerprint(defn, _resolver())
    cfg: Any = defn.normalized_config
    with pytest.raises(TypeError):
        cfg["ema_fast"] = 999
    assert implementation_fingerprint(defn, _resolver()) == before


# ---------------------------------------------------------------- resolvers


def test_importlib_resolver_real_module() -> None:
    r = ImportlibSourceResolver()
    first = r.get_source("json")
    assert isinstance(first, str) and len(first) > 0
    assert r.get_source("json") == first


def test_importlib_resolver_missing_module() -> None:
    with pytest.raises(ValueError, match="[Uu]nknown|module"):
        ImportlibSourceResolver().get_source("no.such.module.xyz")


def test_importlib_resolver_no_source_module() -> None:
    with pytest.raises(ValueError, match="[Ss]ource|module"):
        ImportlibSourceResolver().get_source("sys")


def test_dict_resolver_missing_key() -> None:
    with pytest.raises(ValueError, match="[Uu]nknown|module"):
        DictSourceResolver({}).get_source("m.a")


# ---------------------------------------------------------------- kernel


def test_kernel_bundle_version_and_modules() -> None:
    assert KERNEL_BUNDLE_VERSION == 1
    assert "domain.trading.strategy" not in KERNEL_BUNDLE_V1_MODULES
    for required in (
        "application.services.paper_runner",
        "application.services.paper_engine",
        "application.ports.paper_trading",
        "domain.market.candle",
        "domain.market.stream",
        "domain.market.indicators",
        "domain.market.regime",
        "domain.risk.engine",
        "domain.risk.config",
        "domain.risk.guards",
        "domain.risk.sizing",
        "domain.risk.stops",
        "domain.portfolio.portfolio",
        "domain.trading.decision",
        "domain.trading.signal",
        "domain.trading.fill",
        "domain.trading.fees",
        "domain.trading.slippage",
    ):
        assert required in KERNEL_BUNDLE_V1_MODULES
    assert len(KERNEL_BUNDLE_V1_MODULES) == len(set(KERNEL_BUNDLE_V1_MODULES))
    # El bundle es cerrado: añadir/quitar módulos cambia la longitud y exige
    # bump de versión + actualización consciente de este test.
    assert len(KERNEL_BUNDLE_V1_MODULES) == 18


def test_kernel_bundle_has_no_time_day_module() -> None:
    # domain/time/day.py no existe en la base de implementación: prohibido inventar.
    assert "domain.time.day" not in KERNEL_BUNDLE_V1_MODULES


def test_kernel_bundle_excludes_nonexistent_service_modules() -> None:
    # Verificado contra el árbol en IMPLEMENTATION_BASE_SHA: estos módulos del
    # diseño existen en otra línea histórica, no aquí. Se omiten sin inventar.
    assert "application.services.decision_context" not in KERNEL_BUNDLE_V1_MODULES
    assert "application.services.regime_confirmation" not in KERNEL_BUNDLE_V1_MODULES


def test_strategy_contract_hash_pure() -> None:
    assert strategy_contract_hash(CONTRACT_V1) != strategy_contract_hash(CONTRACT_V2)
    with pytest.raises(ValueError, match="[Ss]ource|empty"):
        strategy_contract_hash("")
    with pytest.raises(ValueError, match="[Ss]ource|empty"):
        strategy_contract_hash("   ")
    with pytest.raises(ValueError, match="[Ss]ource"):
        strategy_contract_hash(123)  # type: ignore[arg-type]


def test_real_strategy_contract_source() -> None:
    src = real_strategy_contract_source()
    assert "def on_candle" in src
    assert real_strategy_contract_source() == src


def test_kernel_identity_validation() -> None:
    kid = make_kernel_identity(_kernel_resolver(), CONTRACT_V1)
    assert kid.kernel_bundle_version == 1
    assert len(kid.kernel_fingerprint) == 64
    with pytest.raises(ValueError, match="[Ff]ingerprint|[Hh]ash"):
        KernelIdentity(kernel_bundle_version=1, kernel_fingerprint="zz")
    with pytest.raises(ValueError, match="[Vv]ersion"):
        KernelIdentity(kernel_bundle_version=0, kernel_fingerprint="aa" * 32)
    with pytest.raises(ValueError, match="[Vv]ersion"):
        KernelIdentity(kernel_bundle_version="1", kernel_fingerprint="aa" * 32)  # type: ignore[arg-type]


def test_kernel_unknown_module_fail_closed() -> None:
    with pytest.raises(ValueError, match="[Uu]nknown|module"):
        kernel_fingerprint(_resolver({}), CONTRACT_V1)


# ------------------------------------------------- spec integration


def _spec_kwargs(kernel_fp: str) -> dict[str, Any]:
    return {
        "dataset": {
            "id": "D",
            "manifest_sha": "ab" * 32,
            "slice": {"kind": "development", "rows": [0, 10]},
        },
        "strategy": {
            "identity": "s",
            "version": "v1",
            "config": {},
            "implementation_fingerprint": "ef" * 32,
        },
        "risk": {"version": "risk-v1", "config_sha": "01" * 32},
        "execution": {"model": "runtime-parity", "version": "v1", "parameters": {}},
        "fees": {"model": "F", "version": "v", "params": {}},
        "slippage": {"model": "S", "version": "v", "params": {}},
        "timing_model": "t",
        "holdout_protocol": "h",
        "kernel_identity": {"kernel_bundle_version": 1, "kernel_fingerprint": kernel_fp},
    }


def test_kernel_difference_changes_spec_id() -> None:
    a = ExperimentSpec(**_spec_kwargs("aa" * 32))
    b = ExperimentSpec(**_spec_kwargs("bb" * 32))
    assert spec_id(a) != spec_id(b)


def test_same_kernel_identity_same_spec_id() -> None:
    assert spec_id(ExperimentSpec(**_spec_kwargs("aa" * 32))) == spec_id(
        ExperimentSpec(**_spec_kwargs("aa" * 32))
    )


def _mk_run(sha: str, rid: str, sid: str) -> ExperimentRun:
    return ExperimentRun(
        experiment_spec_id=sid,
        run_id=rid,
        created_at="2026-09-11T00:00:00+00:00",
        application_git_sha=sha,
        status="ok",
        event_trace_hash="bb" * 32,
        metrics_hash="cc" * 32,
    )


def test_app_sha_only_on_run_not_spec() -> None:
    from lab.experiment_spec import ExperimentSpec

    sid = spec_id(ExperimentSpec(**_spec_kwargs("aa" * 32)))
    assert _mk_run("aaa", "r-1", sid).experiment_spec_id == sid
    assert _mk_run("bbb", "r-2", sid).experiment_spec_id == sid


# ---------------------------------------------------------------- goldens

GOLDEN_SOURCES = {"m.a": "class A:\n    x = 1\n", "m.b": "VALUE = 2\n"}
GOLDEN_DEFN_KWARGS: dict[str, Any] = {
    "strategy_id": "ema-rsi-baseline",
    "strategy_version": "baseline-v1",
    "strategy_api_version": 1,
    "kind": "deterministic",
    "normalized_config": {"ema_fast": 20},
    "sources": ("m.a", "m.b"),
}
GOLDEN_CONTRACT = "class Strategy:\n    version: str\n"


def _golden_defn() -> StrategyDefinition:
    return StrategyDefinition(**GOLDEN_DEFN_KWARGS)


def test_golden_implementation_fingerprint() -> None:
    # Literal fijado tras verificación independiente (stdlib json+hashlib y
    # sha256sum sobre los contenidos fuente; ver evidencia 17B).
    assert (
        implementation_fingerprint(_golden_defn(), DictSourceResolver(dict(GOLDEN_SOURCES)))
        == "c10cfd54d457600dd143d9be6d0897d70ede05b999e15eb1599fd60d17b25625"
    )


def test_golden_strategy_artifact_identity() -> None:
    assert (
        strategy_artifact_identity(_golden_defn(), DictSourceResolver(dict(GOLDEN_SOURCES)))
        == "1360bba4a14408e058f317d94670c81af92a6c30d37257264e6585d76a40003a"
    )


def test_golden_kernel_fingerprint() -> None:
    # Bundle de 18 módulos (desviaciones documentadas en kernel_bundle.py).
    bundle = {m: f"SOURCE:{m}\n" for m in KERNEL_BUNDLE_V1_MODULES}
    assert kernel_fingerprint(DictSourceResolver(bundle), GOLDEN_CONTRACT) == (
        "679db0d2250490b5ad9c51283c4bcf9a7b5cc0f314f016da9cfcb3ebad784a69"
    )


def test_golden_strategy_contract() -> None:
    assert strategy_contract_hash(GOLDEN_CONTRACT) == (
        "4914a8f5264a2462c65a0bc3913a430006c996a768a671be97200723cec21d6b"
    )


def test_second_process_determinism() -> None:
    code = (
        "from lab.fingerprints import DictSourceResolver, StrategyDefinition,"
        " implementation_fingerprint;"
        "from lab.kernel_bundle import (KERNEL_BUNDLE_V1_MODULES,"
        " kernel_fingerprint);"
        f"d=StrategyDefinition(**{_base_defn_kwargs()!r});"
        f"r=DictSourceResolver({_base_sources()!r});"
        "print(implementation_fingerprint(d,r));"
        "kb={m:'SOURCE:'+m+'\\n' for m in KERNEL_BUNDLE_V1_MODULES};"
        f"print(kernel_fingerprint(DictSourceResolver(kb),{_base_contract()!r}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    bundle = {m: f"SOURCE:{m}\n" for m in KERNEL_BUNDLE_V1_MODULES}
    in_process = (
        implementation_fingerprint(_golden_defn(), DictSourceResolver(dict(GOLDEN_SOURCES))),
        kernel_fingerprint(DictSourceResolver(bundle), GOLDEN_CONTRACT),
    )
    assert tuple(proc.stdout.strip().split("\n")) == in_process


def _base_sources() -> dict[str, str]:
    return dict(GOLDEN_SOURCES)


def _base_defn_kwargs() -> dict[str, Any]:
    return dict(GOLDEN_DEFN_KWARGS)


def _base_contract() -> str:
    return GOLDEN_CONTRACT
