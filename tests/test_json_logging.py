import io
import json
import logging
from typing import Any

from infrastructure.observability.logging import (
    BUY_FILL,
    EXCEPTION,
    IMPORTANT_RISK_REJECTION,
    PROCESS_START,
    JsonFormatter,
    StructuredLogger,
    is_important_risk_rejection,
)


def _captured_logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"test-json-logging-{id(stream)}")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return logger, stream


def _lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_json_logger_emits_valid_json() -> None:
    logger, stream = _captured_logger()
    structured = StructuredLogger(logger, context={"session_id": "s", "symbol": "ETHUSDT"})
    structured.info(PROCESS_START, application_version="0.1.3")

    records = _lines(stream)
    assert len(records) == 1
    rec = records[0]
    assert rec["event"] == PROCESS_START
    assert rec["level"] == "INFO"
    assert rec["session_id"] == "s"
    assert rec["symbol"] == "ETHUSDT"
    assert rec["application_version"] == "0.1.3"
    assert rec["timestamp"].endswith("+00:00")


def test_json_logger_fill_event() -> None:
    logger, stream = _captured_logger()
    structured = StructuredLogger(logger, context={"session_id": "s"})
    structured.info(BUY_FILL, symbol="ETHUSDT", timeframe="15m", exec_price=2503.33)

    records = _lines(stream)
    assert records[0]["event"] == BUY_FILL
    assert records[0]["exec_price"] == 2503.33
    assert records[0]["timeframe"] == "15m"


def test_json_logger_important_risk_rejection() -> None:
    logger, stream = _captured_logger()
    structured = StructuredLogger(logger, context={"session_id": "s"})
    structured.warning(IMPORTANT_RISK_REJECTION, risk_reason="max_daily_loss")

    records = _lines(stream)
    assert records[0]["event"] == IMPORTANT_RISK_REJECTION
    assert records[0]["level"] == "WARNING"
    assert records[0]["risk_reason"] == "max_daily_loss"


def test_json_logger_exception() -> None:
    logger, stream = _captured_logger()
    structured = StructuredLogger(logger, context={"session_id": "s"})
    try:
        raise ValueError("boom")
    except ValueError:
        structured.exception(EXCEPTION)

    records = _lines(stream)
    assert records[0]["event"] == EXCEPTION
    assert records[0]["level"] == "ERROR"
    assert "exception" in records[0]
    assert "ValueError" in records[0]["exception"]


def test_json_logger_no_secrets_in_logs() -> None:
    logger, stream = _captured_logger()
    structured = StructuredLogger(
        logger,
        context={"session_id": "s", "application_version": "0.1.3"},
    )
    structured.info(PROCESS_START, symbol="ETHUSDT")

    raw = stream.getvalue()
    for secret in ("password", "api_key", "token", "secret", "postgres_password"):
        assert secret not in raw.lower()


def test_is_important_risk_rejection() -> None:
    assert is_important_risk_rejection("max_daily_loss") is True
    assert is_important_risk_rejection("max_drawdown") is True
    assert is_important_risk_rejection("kill_switch") is True
    assert is_important_risk_rejection("stop_unavailable") is True
    assert is_important_risk_rejection("no_position_to_reduce") is False
    assert is_important_risk_rejection("") is False


def test_structured_logger_error_method() -> None:
    logger, stream = _captured_logger()
    structured = StructuredLogger(logger, context={"session_id": "s"})
    structured.error("ERROR", message="report write failed")

    records = _lines(stream)
    assert records[0]["event"] == "ERROR"
    assert records[0]["level"] == "ERROR"


def test_configure_json_logging_is_idempotent() -> None:
    from infrastructure.observability.logging import configure_json_logging

    logger = configure_json_logging()
    assert any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers)
    n = len(logger.handlers)
    configure_json_logging()
    assert len(logger.handlers) == n
