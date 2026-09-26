import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from ragdb.desktop.theme import DARK, LIGHT, ThemeManager, ThemeMode
from ragdb.desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def ui(tmp_path):
    palette, stylesheet = QPalette(APP.palette()), APP.styleSheet()
    manager = ThemeManager(QSettings(str(tmp_path / "theme.ini"), QSettings.Format.IniFormat))
    manager.set_reduce_motion(True)
    window = MainWindow(theme_manager=manager)
    window.show()
    APP.processEvents()
    yield window, manager
    window.close()
    window.deleteLater()
    APP.processEvents()
    APP.setPalette(palette)
    APP.setStyleSheet(stylesheet)


def background(window):
    image = window.grab().toImage()
    point = window.pages.mapTo(window, window.pages.rect().center())
    ratio = image.devicePixelRatio()
    return image.pixelColor(int(point.x() * ratio), int(point.y() * ratio)).name()


def test_actual_icon_switch_changes_rendered_background_and_persists(ui):
    window, manager = ui
    for mode, colors in ((ThemeMode.LIGHT, LIGHT), (ThemeMode.DARK, DARK), (ThemeMode.LIGHT, LIGHT)):
        window.top_bar.theme.buttons[mode].click()
        APP.processEvents()
        assert manager.mode is mode
        assert manager.settings.value("appearance/theme") == mode.value
        assert background(window) == colors["window"]
        assert APP.palette().color(QPalette.ColorRole.Base).name() == colors["panel"]


def test_system_scheme_notifications_update_only_follow_system(ui):
    window, manager = ui
    window.top_bar.theme.buttons[ThemeMode.SYSTEM].click()
    assert window.top_bar.theme.buttons[ThemeMode.SYSTEM].isChecked()
    assert sum(button.isChecked() for button in window.top_bar.theme.buttons.values()) == 1
    for scheme, colors in ((Qt.ColorScheme.Dark, DARK), (Qt.ColorScheme.Light, LIGHT)):
        APP.styleHints().colorSchemeChanged.emit(scheme)
        APP.processEvents()
        assert background(window) == colors["window"]
        assert manager.settings.value("appearance/theme") == "system"
    manager.set_mode("dark")
    APP.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    APP.processEvents()
    assert background(window) == DARK["window"]
    manager.set_mode("system")
    APP.processEvents()
    assert background(window) == LIGHT["window"]  # no feedback from our dark palette


def test_click_randomizes_indicator_but_repainting_does_not(ui):
    window, manager = ui
    manager.set_mode(ThemeMode.LIGHT)
    for index, button in enumerate(window.navigation.buttons):
        for _ in range(4):
            before = button.indicator_color.name()
            button.click()
            APP.processEvents()
            current = button.indicator_color.name()
            assert current != before
            assert current in {pair[0] for pair in button.LINE_COLORS}
            assert window.pages.currentIndex() == index
            button.grab()
            assert button.indicator_color.name() == current
    manager.set_mode(ThemeMode.DARK)
    assert all(b.indicator_color.name() in {pair[1] for pair in b.LINE_COLORS}
               for b in window.navigation.buttons)


def test_inactive_theme_manager_cannot_override_active_manual_theme(ui, tmp_path):
    window, current = ui
    old = ThemeManager(QSettings(str(tmp_path / "old.ini"), QSettings.Format.IniFormat))
    old.set_mode("system")
    current.set_mode("dark")
    APP.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Light)
    APP.processEvents()
    assert old.resolved_mode() is ThemeMode.LIGHT
    assert background(window) == DARK["window"]
    assert current.mode is ThemeMode.DARK
