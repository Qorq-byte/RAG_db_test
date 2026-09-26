"""Desktop application entry point."""

import sys
import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ragdb.desktop.startup import WelcomeWindow
from ragdb.desktop.theme import ThemeManager


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    theme_manager = ThemeManager()
    theme_manager.apply()
    window = WelcomeWindow(theme_manager)
    window.show()
    exit_after_ms = os.environ.get("RAGDB_GUI_TEST_EXIT_MS")
    if exit_after_ms:
        QTimer.singleShot(int(exit_after_ms), application.quit)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
