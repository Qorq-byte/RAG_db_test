"""Logging setup with optional sensitive-value redaction."""

import logging
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler


class RedactingFilter(logging.Filter):
    """Replace configured secret values before a record reaches handlers."""

    def __init__(self, sensitive_values: Iterable[str] = ()) -> None:
        super().__init__()
        self._sensitive_values = tuple(value for value in sensitive_values if value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for value in self._sensitive_values:
            message = message.replace(value, "***")
        record.msg = message
        record.args = ()
        return True


def configure_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    sensitive_values: Iterable[str] = (),
) -> None:
    """Configure console logging and an optional rotating file handler."""

    handlers: list[logging.Handler] = [
        RichHandler(rich_tracebacks=True, show_path=False)
    ]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        )

    redacting_filter = RedactingFilter(sensitive_values)
    for handler in handlers:
        handler.addFilter(redacting_filter)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )
