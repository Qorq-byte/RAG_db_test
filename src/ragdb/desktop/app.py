"""Desktop application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from ragdb.desktop.window import MainWindow
from ragdb.runtime import ApplicationRuntime


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(ApplicationRuntime.from_config())
    window.show()
    return application.exec()
