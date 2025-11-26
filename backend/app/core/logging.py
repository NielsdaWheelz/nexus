"""Structured JSON logging configuration.

This module configures Python logging with JSON output format, enabling
structured log querying and correlation via trace IDs.

All logs are written to STDOUT as single JSON lines with fields:
- ts: ISO8601 timestamp
- level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- logger: Logger name
- event: High-level event name (request_completed, error_occurred, etc.)
- method: HTTP method (for request logs)
- path: HTTP path (for request logs)
- status: HTTP status code (for request logs)
- duration_ms: Request duration in milliseconds (for request logs)
- trace_id: Request trace ID for correlation
- error_code: Canonical error code (if error)
- user_id: Authenticated user ID (if available, null for now)
- message: Log message
"""

import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Custom log formatter that outputs JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: LogRecord to format

        Returns:
            JSON string suitable for structured logging
        """
        log_obj: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from LogRecord
        if hasattr(record, "trace_id"):
            log_obj["trace_id"] = record.trace_id
        if hasattr(record, "event"):
            log_obj["event"] = record.event
        if hasattr(record, "method"):
            log_obj["method"] = record.method
        if hasattr(record, "path"):
            log_obj["path"] = record.path
        if hasattr(record, "status"):
            log_obj["status"] = record.status
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        if hasattr(record, "user_id"):
            log_obj["user_id"] = record.user_id
        if hasattr(record, "error_code"):
            log_obj["error_code"] = record.error_code

        # Add exception info if present
        if record.exc_info and record.exc_text:
            log_obj["exception"] = record.exc_text

        return json.dumps(log_obj)


def configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structured logging with JSON output.

    Args:
        log_level: Python logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format (json for structured, text for human-readable)
    """
    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": JSONFormatter,
            },
            "text": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "default": {
                "level": log_level,
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": log_format,
            },
        },
        "root": {
            "level": log_level,
            "handlers": ["default"],
        },
        "loggers": {
            "app": {
                "level": log_level,
                "handlers": ["default"],
                "propagate": True,
            },
        },
    }

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with structured logging.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
