"""Desktop application entry point."""

import sys
import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ragdb.desktop.window import MainWindow
from ragdb.runtime import ApplicationRuntime


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(ApplicationRuntime.from_config())
    window.show()
    exit_after_ms = os.environ.get("RAGDB_GUI_TEST_EXIT_MS")
    if exit_after_ms:
        QTimer.singleShot(int(exit_after_ms), application.quit)
    return application.exec()
