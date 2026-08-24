from domain.experiments.experiment import ExperimentMetadata, build_experiment_id


def _meta(
    git_commit: str = "abc123",
    dataset_version: str = "BYBIT_ETHBTC_V001",
    strategy_version: str = "baseline-v1",
    feature_config_version: str = "v1",
    fees_model_version: str = "bybit-spot-v1",
    slippage_model_version: str = "conservative-v1",
    prompt_version: str = "",
    llm_provider: str = "",
    llm_model: str = "",
    embedding_provider: str = "",
    embedding_model: str = "",
    risk_config_version: str = "",
    random_seed: int = 42,
    params: tuple[tuple[str, str], ...] = (),
    started_at: str = "",
    finished_at: str = "",
) -> ExperimentMetadata:
    return ExperimentMetadata(
        git_commit=git_commit,
        dataset_version=dataset_version,
        strategy_version=strategy_version,
        feature_config_version=feature_config_version,
        fees_model_version=fees_model_version,
        slippage_model_version=slippage_model_version,
        prompt_version=prompt_version,
        llm_provider=llm_provider,
        llm_model=llm_model,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        risk_config_version=risk_config_version,
        random_seed=random_seed,
        params=params,
        started_at=started_at,
        finished_at=finished_at,
    )


def test_same_params_same_id() -> None:
    assert build_experiment_id(_meta()) == build_experiment_id(_meta())


def test_changing_a_param_changes_id() -> None:
    base = build_experiment_id(_meta())
    assert build_experiment_id(_meta(random_seed=43)) != base
    assert build_experiment_id(_meta(strategy_version="baseline-v2")) != base


def test_timestamps_do_not_affect_id() -> None:
    a = _meta(started_at="2026-01-01T00:00:00", finished_at="2026-01-02T00:00:00")
    b = _meta(started_at="2027-01-01T00:00:00", finished_at="2027-01-02T00:00:00")
    assert build_experiment_id(a) == build_experiment_id(b)


def test_params_order_invariant() -> None:
    a = _meta(params=(("a", "1"), ("b", "2")))
    b = _meta(params=(("b", "2"), ("a", "1")))
    assert build_experiment_id(a) == build_experiment_id(b)


def test_id_is_hex16() -> None:
    eid = build_experiment_id(_meta())
    assert len(eid) == 16
    assert all(c in "0123456789abcdef" for c in eid)


def test_llm_fields_affect_id() -> None:
    base = build_experiment_id(_meta())
    assert build_experiment_id(_meta(prompt_version="v002")) != base
    assert build_experiment_id(_meta(llm_provider="openai")) != base
    assert build_experiment_id(_meta(llm_model="deepseek-v4-pro")) != base


def test_new_fields_default_to_empty() -> None:
    m = _meta()
    assert m.prompt_version == ""
    assert m.llm_provider == ""
    assert m.risk_config_version == ""
