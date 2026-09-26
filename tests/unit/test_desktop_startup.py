import os
from threading import Event
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow

from ragdb.desktop.startup import STARTUP_ERROR, WelcomeWindow
from ragdb.desktop.theme import ThemeManager


APPLICATION = QApplication.instance() or QApplication([])


def wait_until(predicate):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        APPLICATION.processEvents()
        QTest.qWait(5)
    APPLICATION.processEvents()
    assert predicate()


@pytest.fixture
def theme(tmp_path):
    return ThemeManager(QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat))


def test_first_window_is_welcome_and_does_not_initialize_runtime(theme):
    calls = []
    window = WelcomeWindow(theme, runtime_factory=lambda: calls.append("runtime"))
    window.show()
    APPLICATION.processEvents()
    try:
        assert window.page.isVisible()
        assert not window.page.enter_button.isVisible()
        window.page.finish_animation()
        assert window.page.enter_button.isVisible()
        assert calls == [] and window.workbench is None
    finally:
        window.close()


def test_enter_creates_runtime_once_off_thread_and_workbench_on_gui_thread(theme):
    started, release = Event(), Event()
    calls = []
    runtime = object()

    def create_runtime():
        assert QThread.currentThread() != APPLICATION.thread()
        calls.append("runtime")
        started.set()
        assert release.wait(5)
        return runtime

    def create_workbench(value, manager):
        assert QThread.currentThread() == APPLICATION.thread()
        assert value is runtime and manager is theme
        calls.append("workbench")
        return QMainWindow()

    window = WelcomeWindow(theme, runtime_factory=create_runtime, workbench_factory=create_workbench)
    window.resize(1100, 700)
    window.show()
    window.page.finish_animation()
    window.page.enter_button.click()
    try:
        assert started.wait(5)
        window.page.enter_button.click()
        window._start()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        wait_until(lambda: bool(ticks))
        assert window.busy and calls == ["runtime"]
        window.close()
        assert window.isVisible()
        assert "等待" in window.page.feedback.text()
    finally:
        release.set()
        wait_until(lambda: not window.busy)
    assert calls == ["runtime", "workbench"]
    assert not window.isVisible() and window.workbench.isVisible()
    assert window.workbench.size() == window.size()
    window.workbench.close()


@pytest.mark.parametrize("failure_stage", ["runtime", "workbench"])
def test_failed_initialization_is_sanitized_and_can_retry(theme, failure_stage):
    attempts = []

    def runtime_factory():
        attempts.append("runtime")
        if failure_stage == "runtime" and len(attempts) == 1:
            raise ValueError("private-test-secret invalid config")
        return object()

    def workbench_factory(runtime, manager):
        if failure_stage == "workbench" and len(attempts) == 1:
            raise ValueError("private-test-secret widget failure")
        return QMainWindow()

    window = WelcomeWindow(theme, runtime_factory=runtime_factory, workbench_factory=workbench_factory)
    window.show()
    window.page.finish_animation()
    window.page.enter_button.click()
    wait_until(lambda: not window.busy)
    assert window.isVisible() and window.workbench is None
    assert window.page.feedback.text() == STARTUP_ERROR
    assert "private-test-secret" not in window.page.feedback.text()
    assert window.page.enter_button.isEnabled()
    window.page.enter_button.click()
    wait_until(lambda: window.workbench is not None)
    assert len(attempts) == 2
    window.workbench.close()


def test_handoff_preserves_maximized_state(theme):
    window = WelcomeWindow(theme, runtime_factory=lambda: object(), workbench_factory=lambda *_: QMainWindow())
    window.showMaximized()
    APPLICATION.processEvents()
    window.page.finish_animation()
    window.page.enter_button.click()
    wait_until(lambda: window.workbench is not None)
    assert window.workbench.isMaximized()
    window.workbench.close()


def test_real_workbench_navigation_after_welcome(theme, tmp_path):
    from ragdb.config import AppSettings, StorageSettings
    from ragdb.infrastructure.database import SQLiteDatabase
    from ragdb.runtime import ApplicationRuntime

    config = tmp_path / "config.toml"
    config.write_text(f"[storage]\ndata_dir = '{tmp_path.as_posix()}'\n", encoding="utf-8")

    def runtime_factory():
        database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
        database.initialize()
        return ApplicationRuntime(AppSettings(storage=StorageSettings(data_dir=tmp_path)), database, config)

    window = WelcomeWindow(theme, runtime_factory=runtime_factory)
    window.show()
    window.page.finish_animation()
    window.page.enter_button.click()
    wait_until(lambda: window.workbench is not None)
    try:
        main = window.workbench
        assert main.isVisible() and main.pages.count() == 7
        main.navigation.select_page(2)
        assert main.pages.currentIndex() == 2
        main.navigation.select_page(6)
        assert main.pages.currentWidget() is main.model_settings_page
    finally:
        window.workbench.close()
