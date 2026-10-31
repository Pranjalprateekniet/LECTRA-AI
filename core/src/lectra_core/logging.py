"""Structured logging configuration with JSON and console formats."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from lectra_core.config import Settings

# Sensitive key patterns to mask from logs
SENSITIVE_KEYS = {
    "key",
    "secret",
    "password",
    "token",
    "authorization",
    "api_key",
    "groq_api_key",
    "qdrant_api_key",
}


def sanitize_value(key: str, value: Any) -> Any:
    """Mask sensitive string values if their key matches known sensitive patterns."""
    if any(s in key.lower() for s in SENSITIVE_KEYS):
        if isinstance(value, str) and value:
            return f"{value[:3]}...[REDACTED]" if len(value) > 6 else "[REDACTED]"
    return value


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize keys and values in a dictionary."""
    sanitized: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        else:
            sanitized[k] = sanitize_value(k, v)
    return sanitized


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as structured, single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        log_entry: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields attached to the log record
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
        }
        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extra_fields:
            log_entry["extra"] = sanitize_dict(extra_fields)

        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter with color-coded levels for local development."""

    COLORS = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        color = self.COLORS.get(record.levelno, self.RESET)
        message = record.getMessage()

        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
        }
        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        extra_str = f" | {sanitize_dict(extra_fields)}" if extra_fields else ""

        formatted = (
            f"{timestamp} [{color}{record.levelname:<8}{self.RESET}] "
            f"{record.name}: {message}{extra_str}"
        )
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
        return formatted


def setup_logging(settings: Settings) -> None:
    """Configure root logger using application settings."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(StructuredJSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Retrieve named logger."""
    return logging.getLogger(name)
