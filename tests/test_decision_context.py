import pytest

from application.services.decision_context import (
    SCHEMA_VERSION,
    DecisionContext,
    validate_decision_context,
)


def _context() -> DecisionContext:
    return DecisionContext(
        schema_version=SCHEMA_VERSION,
        signal_reason="ema_cross_up",
        atr=12.34,
        ema_fast=2502.1,
        ema_slow=2490.7,
        rsi=55.2,
        regime="SIDEWAYS",
    )


def test_decision_context_jsonb_roundtrip() -> None:
    ctx = _context()
    assert DecisionContext.from_dict(ctx.to_dict()) == ctx


def test_decision_context_roundtrip_preserves_nones() -> None:
    ctx = DecisionContext(
        schema_version=SCHEMA_VERSION,
        signal_reason="warmup",
        atr=None,
        ema_fast=None,
        ema_slow=None,
        rsi=None,
        regime=None,
    )
    assert DecisionContext.from_dict(ctx.to_dict()) == ctx


def test_validate_decision_context_accepts_current_schema() -> None:
    validate_decision_context(_context().to_dict())


def test_validate_decision_context_rejects_wrong_schema_version() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        validate_decision_context({**_context().to_dict(), "schema_version": 999})


def test_validate_decision_context_rejects_missing_schema_version() -> None:
    d = _context().to_dict()
    del d["schema_version"]
    with pytest.raises(ValueError, match="schema_version"):
        validate_decision_context(d)


def test_validate_decision_context_rejects_missing_signal_reason() -> None:
    d = _context().to_dict()
    del d["signal_reason"]
    with pytest.raises(ValueError, match="signal_reason"):
        validate_decision_context(d)


def test_validate_decision_context_rejects_non_dict() -> None:
    with pytest.raises(ValueError, match="object"):
        validate_decision_context("not a dict")  # type: ignore[arg-type]
