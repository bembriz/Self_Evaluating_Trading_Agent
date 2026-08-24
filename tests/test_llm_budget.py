from domain.llm.budget import Budget, BudgetLevel, BudgetState, max_level


def test_budget_levels_thresholds() -> None:
    assert Budget(100.0, 0.0).level() is BudgetLevel.OK
    assert Budget(100.0, 49.9).level() is BudgetLevel.OK
    assert Budget(100.0, 50.0).level() is BudgetLevel.ALERT_50
    assert Budget(100.0, 75.0).level() is BudgetLevel.ALERT_75
    assert Budget(100.0, 90.0).level() is BudgetLevel.ALERT_90
    assert Budget(100.0, 100.0).level() is BudgetLevel.BLOCKED
    assert Budget(100.0, 150.0).level() is BudgetLevel.BLOCKED


def test_budget_consume_is_immutable() -> None:
    b = Budget(100.0, 40.0)
    b2 = b.consume(20.0)
    assert b.consumed_usd == 40.0
    assert b2.consumed_usd == 60.0
    assert b2.level() is BudgetLevel.ALERT_50


def test_budget_zero_limit_never_blocks() -> None:
    assert Budget(0.0, 0.0).is_blocked() is False


def test_state_records_both_and_blocks() -> None:
    s = BudgetState(experiment=Budget(10.0), monthly=Budget(1000.0))
    s2 = s.record(6.0)
    assert s2.experiment.consumed_usd == 6.0
    assert s2.monthly.consumed_usd == 6.0
    assert s2.experiment.level() is BudgetLevel.ALERT_50
    assert s2.is_blocked() is False
    assert s2.record(4.0).experiment.is_blocked() is True
    assert s2.record(4.0).is_blocked() is True


def test_max_level_picks_more_severe() -> None:
    assert max_level(BudgetLevel.OK, BudgetLevel.ALERT_90) is BudgetLevel.ALERT_90
    assert max_level(BudgetLevel.BLOCKED, BudgetLevel.OK) is BudgetLevel.BLOCKED
