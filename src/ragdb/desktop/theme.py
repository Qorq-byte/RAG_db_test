"""Application theme tokens and persisted appearance preferences."""

from enum import StrEnum
from weakref import ref

from PySide6.QtCore import QObject, QSettings, Signal, Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


LIGHT = {
    "window": "#f6f7f9",
    "sidebar": "#eef1f5",
    "panel": "#ffffff",
    "raised": "#f9fafb",
    "text": "#18202b",
    "muted": "#687386",
    "border": "#dce2ea",
    "accent": "#0f8aa6",
    "accent_soft": "#d9f1f6",
    "danger": "#c94747",
    "success": "#23845f",
    "warning": "#a66b13",
}
DARK = {
    "window": "#101419",
    "sidebar": "#0b0f14",
    "panel": "#171c23",
    "raised": "#1d242d",
    "text": "#e8edf4",
    "muted": "#8d99aa",
    "border": "#2a333f",
    "accent": "#43c2dc",
    "accent_soft": "#163841",
    "danger": "#ef7171",
    "success": "#55c596",
    "warning": "#e5aa52",
}


class ThemeManager(QObject):
    changed = Signal(str, bool)

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        app = QApplication.instance()
        self._system_scheme = app.styleHints().colorScheme() if app else Qt.ColorScheme.Unknown
        self._fallback_dark = bool(app and app.style().standardPalette().color(QPalette.ColorRole.Window).lightness() < 128)
        if app:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        self.settings = settings or QSettings("ragdb", "ragdb-gui")
        self.mode = ThemeMode(
            self.settings.value("appearance/theme", ThemeMode.SYSTEM.value)
        )
        self.reduce_motion = self.settings.value(
            "appearance/reduce_motion", False, type=bool
        )

    def resolved_mode(self) -> ThemeMode:
        if self.mode is not ThemeMode.SYSTEM:
            return self.mode
        if self._system_scheme == Qt.ColorScheme.Dark:
            return ThemeMode.DARK
        if self._system_scheme == Qt.ColorScheme.Light:
            return ThemeMode.LIGHT
        return ThemeMode.DARK if self._fallback_dark else ThemeMode.LIGHT

    def _system_scheme_changed(self, scheme):
        self._system_scheme = scheme
        app = QApplication.instance()
        owner = getattr(app, "_ragdb_theme_owner", lambda: None)
        if self.mode is ThemeMode.SYSTEM and owner() is self:
            self.apply()

    def set_mode(self, mode: ThemeMode | str) -> None:
        # QVariant converts StrEnum item data to str when read from QComboBox.
        self.mode = ThemeMode(mode)
        self.settings.setValue("appearance/theme", self.mode.value)
        self.apply()

    def set_reduce_motion(self, enabled: bool) -> None:
        self.reduce_motion = enabled
        self.settings.setValue("appearance/reduce_motion", enabled)
        app = QApplication.instance()
        if app and getattr(app, "_ragdb_theme_owner", lambda: None)() is self:
            from ragdb.desktop.wet_paint import install_wet_paint
            install_wet_paint(app, enabled)
        self.changed.emit(self.resolved_mode().value, enabled)

    def sidebar_width(self) -> int:
        """Return the persisted expanded sidebar width within safe bounds."""
        return self._bounded_int("layout/sidebar_width", 236, 160, 400)

    def set_sidebar_width(self, width: int) -> None:
        self.settings.setValue("layout/sidebar_width", max(160, min(400, width)))

    def sidebar_collapsed(self) -> bool:
        return self.settings.value("layout/sidebar_collapsed", False, type=bool)

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.settings.setValue("layout/sidebar_collapsed", collapsed)

    def sidebar_footer_visible(self) -> bool:
        return self.settings.value("layout/sidebar_footer_visible", True, type=bool)

    def set_sidebar_footer_visible(self, visible: bool) -> None:
        self.settings.setValue("layout/sidebar_footer_visible", visible)

    def detail_panel_visible(self) -> bool:
        return self.settings.value("layout/detail_panel_visible", True, type=bool)

    def set_detail_panel_visible(self, visible: bool) -> None:
        self.settings.setValue("layout/detail_panel_visible", visible)

    def _bounded_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, value))

    def apply(self) -> None:
        app = QApplication.instance()
        resolved = self.resolved_mode()
        if app is not None:
            app._ragdb_theme_owner = ref(self)
            colors = DARK if resolved is ThemeMode.DARK else LIGHT
            palette = QPalette(app.palette())
            roles = {
                QPalette.ColorRole.Window: "window", QPalette.ColorRole.WindowText: "text",
                QPalette.ColorRole.Base: "panel", QPalette.ColorRole.AlternateBase: "raised",
                QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "raised",
                QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.ToolTipBase: "raised",
                QPalette.ColorRole.ToolTipText: "text", QPalette.ColorRole.Highlight: "accent",
                QPalette.ColorRole.HighlightedText: "window", QPalette.ColorRole.Link: "accent",
            }
            for role, token in roles.items():
                palette.setColor(role, QColor(colors[token]))
            app.setPalette(palette)
            app.setStyleSheet(build_stylesheet(colors))
            from ragdb.desktop.wet_paint import install_wet_paint
            install_wet_paint(app, self.reduce_motion)
        self.changed.emit(resolved.value, self.reduce_motion)



def build_stylesheet(tokens: dict[str, str]) -> str:
    return f"""
    * {{ font-family: "Segoe UI", "Microsoft YaHei UI"; color: {tokens["text"]}; }}
    QMainWindow, QWidget#appRoot {{ background: {tokens["window"]}; }}
    QWidget#sidebar {{ background: {tokens["sidebar"]}; border-right: 1px solid {tokens["border"]}; }}
    QLabel[navGroup="true"] {{ color: {tokens["muted"]}; font-size: 10px; font-weight: 650; padding: 8px 10px 3px 10px; }}
    QPushButton[navItem="true"] {{ text-align: left; background: transparent; border: none; border-radius: 7px; padding: 7px 10px 7px 34px; color: {tokens["muted"]}; }}
    QPushButton[navItem="true"]:checked {{ color: {tokens["text"]}; font-weight: 650; }}
    QFrame#navHover {{ background: {tokens["accent_soft"]}; border: none; border-radius: 7px; }}
    QWidget#topBar, QFrame[card="true"], QFrame[resultCard="true"], QWidget#detailPanel {{ background: {tokens["panel"]}; border: 1px solid {tokens["border"]}; border-radius: 10px; }}
    QFrame[resultCard="true"]:hover {{ border-color: {tokens["accent"]}; background: {tokens["raised"]}; }}
    QLabel[resultTitle="true"] {{ font-size: 14px; font-weight: 650; }}
    QLabel[muted="true"] {{ color: {tokens["muted"]}; }}
    QLabel[pageTitle="true"] {{ font-size: 24px; font-weight: 650; }}
    QLabel[status="success"] {{ color: {tokens["success"]}; background: {tokens["raised"]}; padding: 3px 8px; border-radius: 8px; }}
    QLabel[status="warning"] {{ color: {tokens["warning"]}; background: {tokens["raised"]}; padding: 3px 8px; border-radius: 8px; }}
    QLabel[status="failure"] {{ color: {tokens["danger"]}; background: {tokens["raised"]}; padding: 3px 8px; border-radius: 8px; }}
    QPushButton, QToolButton {{ background: #6366f1; color: white; border: 2px solid transparent; border-radius: 4px; padding: 8px 14px; font-weight: 600; }}
    QPushButton:hover, QToolButton:hover, QPushButton[wetNear="true"], QToolButton[wetNear="true"] {{ background: #4f46e5; color: white; }}
    QPushButton:focus, QToolButton:focus {{ border-color: #a5b4fc; outline: none; }}
    QComboBox:focus, QListWidget:focus, QTableWidget:focus {{ outline: none; border: 2px solid {tokens["accent"]}; }}
    QPushButton[danger="true"] {{ background: #e11d48; color: white; }}
    QPushButton[danger="true"]:hover, QPushButton[danger="true"][wetNear="true"] {{ background: #be123c; }}
    QPushButton[navItem="true"][wetNear="true"], QPushButton[navItem="true"]:hover {{ background: #4f46e5; color: white; }}
    QToolButton[themeIcon="true"] {{ padding: 0; background: transparent; }}
    QToolButton[themeIcon="true"]:checked {{ background: #6366f1; }}
    QToolButton[themeIcon="true"][wetNear="true"] {{ background: #4f46e5; }}
    QPushButton:disabled, QToolButton:disabled {{ background: {tokens["border"]}; color: {tokens["muted"]}; }}
    QLineEdit, QComboBox, QTextEdit, QTextBrowser, QListWidget, QTableWidget, QTabWidget::pane {{ background: {tokens["panel"]}; border: 1px solid {tokens["border"]}; border-radius: 8px; padding: 7px; selection-background-color: {tokens["accent_soft"]}; }}
    QTabBar::tab {{ padding: 8px 16px; color: {tokens["muted"]}; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ color: {tokens["text"]}; border-bottom-color: {tokens["accent"]}; font-weight: 650; }}
    QHeaderView::section {{ background: {tokens["raised"]}; color: {tokens["muted"]}; border: none; border-bottom: 1px solid {tokens["border"]}; padding: 8px; }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border-color: {tokens["accent"]}; }}
    QToolTip {{ background: {tokens["raised"]}; color: {tokens["text"]}; border: 1px solid {tokens["border"]}; padding: 5px; }}
    """
