import logging
from pathlib import Path

from ragdb.logging import configure_logging


def test_sensitive_values_are_redacted(tmp_path: Path) -> None:
    log_file = tmp_path / "ragdb.log"
    configure_logging(log_file=log_file, sensitive_values=["top-secret"])

    logging.getLogger("ragdb.test").info("token=%s", "top-secret")
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert "top-secret" not in content
    assert "token=***" in content
