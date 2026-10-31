"""Unit tests for structured logging and secret masking."""

import json
import logging

from lectra_core.logging import (
    ConsoleFormatter,
    StructuredJSONFormatter,
    sanitize_dict,
    sanitize_value,
)


def test_sanitize_value():
    """Verify secrets and keys are masked."""
    assert sanitize_value("groq_api_key", "gsk_123456789") == "gsk...[REDACTED]"
    assert sanitize_value("password", "short") == "[REDACTED]"
    assert sanitize_value("regular_field", "regular_value") == "regular_value"


def test_sanitize_dict():
    """Verify recursive dictionary masking."""
    payload = {
        "user_id": "123",
        "nested": {
            "api_key": "secret_token_value",
            "count": 42,
        },
    }
    sanitized = sanitize_dict(payload)
    assert sanitized["user_id"] == "123"
    assert sanitized["nested"]["count"] == 42
    assert "[REDACTED]" in sanitized["nested"]["api_key"]


def test_structured_json_formatter():
    """Verify JSON output structure and extra fields."""
    formatter = StructuredJSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test event message",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-abc"
    record.api_key = "secret_value_123"

    formatted = formatter.format(record)
    data = json.loads(formatted)

    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Test event message"
    assert "timestamp" in data
    assert data["extra"]["job_id"] == "job-abc"
    assert "[REDACTED]" in data["extra"]["api_key"]


def test_console_formatter():
    """Verify console output contains message and level."""
    formatter = ConsoleFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Console message",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "Console message" in formatted
    assert "INFO" in formatted
