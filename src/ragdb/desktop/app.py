"""Desktop application entry point."""

import sys
import os
from pathlib import Path
import argparse

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ragdb.desktop.startup import WelcomeWindow
from ragdb.desktop.theme import ThemeManager


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 知识库桌面工作台")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    options, _ = parser.parse_known_args()
    application = QApplication.instance() or QApplication(sys.argv)
    theme_manager = ThemeManager()
    theme_manager.apply()
    def create_runtime():
        from ragdb.runtime import ApplicationRuntime
        return ApplicationRuntime.from_config(options.config)

    window = WelcomeWindow(theme_manager, runtime_factory=create_runtime)
    window.show()
    exit_after_ms = os.environ.get("RAGDB_GUI_TEST_EXIT_MS")
    if exit_after_ms:
        QTimer.singleShot(int(exit_after_ms), application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
