"""Application theme tokens and persisted appearance preferences."""

from enum import StrEnum

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


LIGHT = {"window": "#f6f7f9", "sidebar": "#eef1f5", "panel": "#ffffff", "raised": "#f9fafb", "text": "#18202b", "muted": "#687386", "border": "#dce2ea", "accent": "#0f8aa6", "accent_soft": "#d9f1f6", "danger": "#c94747", "success": "#23845f", "warning": "#a66b13"}
DARK = {"window": "#101419", "sidebar": "#0b0f14", "panel": "#171c23", "raised": "#1d242d", "text": "#e8edf4", "muted": "#8d99aa", "border": "#2a333f", "accent": "#43c2dc", "accent_soft": "#163841", "danger": "#ef7171", "success": "#55c596", "warning": "#e5aa52"}


class ThemeManager(QObject):
    changed = Signal(str, bool)

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or QSettings("ragdb", "ragdb-gui")
        self.mode = ThemeMode(self.settings.value("appearance/theme", ThemeMode.SYSTEM.value))
        self.reduce_motion = self.settings.value("appearance/reduce_motion", False, type=bool)

    def resolved_mode(self) -> ThemeMode:
        if self.mode is not ThemeMode.SYSTEM:
            return self.mode
        app = QApplication.instance()
        color = app.palette().color(QPalette.ColorRole.Window) if app else None
        return ThemeMode.DARK if color and color.lightness() < 128 else ThemeMode.LIGHT

    def set_mode(self, mode: ThemeMode) -> None:
        self.mode = mode
        self.settings.setValue("appearance/theme", mode.value)
        self.apply()

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduce_motion = enabled
        self.settings.setValue("appearance/reduce_motion", enabled)
        self.changed.emit(self.resolved_mode().value, enabled)

    def apply(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(DARK if self.resolved_mode() is ThemeMode.DARK else LIGHT))
        self.changed.emit(self.resolved_mode().value, self.reduce_motion)


def build_stylesheet(tokens: dict[str, str]) -> str:
    return f"""
    * {{ font-family: "Segoe UI", "Microsoft YaHei UI"; color: {tokens['text']}; }}
    QMainWindow, QWidget#appRoot {{ background: {tokens['window']}; }}
    QWidget#sidebar {{ background: {tokens['sidebar']}; border-right: 1px solid {tokens['border']}; }}
    QWidget#topBar, QFrame[card="true"], QWidget#detailPanel {{ background: {tokens['panel']}; border: 1px solid {tokens['border']}; border-radius: 10px; }}
    QLabel[muted="true"] {{ color: {tokens['muted']}; }}
    QLabel[pageTitle="true"] {{ font-size: 24px; font-weight: 650; }}
    QLabel[status="success"] {{ color: {tokens['success']}; background: {tokens['raised']}; padding: 3px 8px; border-radius: 8px; }}
    QLabel[status="warning"] {{ color: {tokens['warning']}; background: {tokens['raised']}; padding: 3px 8px; border-radius: 8px; }}
    QLabel[status="failure"] {{ color: {tokens['danger']}; background: {tokens['raised']}; padding: 3px 8px; border-radius: 8px; }}
    QPushButton {{ background: {tokens['raised']}; border: 1px solid {tokens['border']}; border-radius: 7px; padding: 7px 12px; }}
    QPushButton:hover {{ border-color: {tokens['accent']}; }}
    QPushButton[primary="true"] {{ background: {tokens['accent']}; color: #071216; border-color: {tokens['accent']}; font-weight: 600; }}
    QPushButton[danger="true"] {{ color: {tokens['danger']}; }}
    QLineEdit, QComboBox, QTextEdit, QTextBrowser, QListWidget, QTableWidget {{ background: {tokens['panel']}; border: 1px solid {tokens['border']}; border-radius: 8px; padding: 7px; selection-background-color: {tokens['accent_soft']}; }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border-color: {tokens['accent']}; }}
    QToolTip {{ background: {tokens['raised']}; color: {tokens['text']}; border: 1px solid {tokens['border']}; padding: 5px; }}
    """
