import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QAbstractAnimation, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ragdb.desktop.theme import ThemeManager, ThemeMode
from ragdb.desktop.welcome import WelcomePage
from ragdb.desktop.welcome_scene import WelcomeScene


APPLICATION = QApplication.instance() or QApplication([])


@pytest.fixture
def theme(tmp_path):
    manager = ThemeManager(QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat))
    manager.set_mode(ThemeMode.LIGHT)
    return manager


@pytest.fixture
def page(theme):
    widget = WelcomePage(theme)
    widget.resize(1280, 800)
    widget.show()
    APPLICATION.processEvents()
    yield widget
    widget.close()
    APPLICATION.processEvents()


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        APPLICATION.processEvents()
        QTest.qWait(5)
    APPLICATION.processEvents()
    assert predicate()


def test_intro_blocks_entry_until_completed_then_requires_click(page):
    entered = []
    page.enter_requested.connect(lambda: entered.append(True))
    assert not page.ready
    assert not page.enter_button.isVisible()
    QTest.keyClick(page, Qt.Key.Key_Return)
    page.enter_button.click()
    assert not entered
    page.animation.setCurrentTime(page.animation.duration())
    APPLICATION.processEvents()
    assert page.ready and page.enter_button.isVisible()
    assert page.enter_button.text() == "欢迎使用RAG系统"
    assert not entered
    page.enter_button.click()
    page.enter_button.click()
    assert entered == [True]


def test_animation_completes_automatically_without_scrolling(theme):
    widget = WelcomePage(theme, duration_ms=40)
    widget.show()
    try:
        wait_until(lambda: widget.ready)
        assert widget.enter_button.isEnabled()
    finally:
        widget.close()


def test_skip_only_reveals_button_and_keyboard_enters(page):
    entered = []
    page.enter_requested.connect(lambda: entered.append(True))
    QTest.keyClick(page, Qt.Key.Key_Escape)
    APPLICATION.processEvents()
    assert page.ready and not entered
    assert page.skip_button.isHidden()
    QTest.keyClick(page.enter_button, Qt.Key.Key_Space)
    assert entered == [True]


def test_reduced_motion_shows_final_state_without_animation(theme):
    theme.set_reduce_motion(True)
    widget = WelcomePage(theme)
    widget.show()
    try:
        APPLICATION.processEvents()
        assert widget.ready
        assert widget.animation.state() is QAbstractAnimation.State.Stopped
        assert widget.reveal.state() is QAbstractAnimation.State.Stopped
        assert all(not card.motion_enabled for card in widget.scene.cards)
    finally:
        widget.close()


def test_hiding_pauses_timeline_and_stops_hover_work(page):
    card = page.scene.cards[0]
    card._animate_flip(1.0)
    page.hide()
    APPLICATION.processEvents()
    assert page.animation.state() is QAbstractAnimation.State.Paused
    assert card.flip.state() is QAbstractAnimation.State.Stopped
    page.show()
    APPLICATION.processEvents()
    assert page.animation.state() is QAbstractAnimation.State.Running
    page.theme_manager.set_reduce_motion(True)
    assert page.ready


@pytest.mark.parametrize("size", [(640, 480), (1280, 800), (1920, 1080)])
def test_ring_and_center_button_fit_after_resize(page, size):
    page.finish_animation()
    page.resize(*size)
    APPLICATION.processEvents()
    viewport = page.scene.sceneRect()
    assert all(viewport.contains(card.sceneBoundingRect()) for card in page.scene.cards)
    center = page.enter_button.mapTo(page, page.enter_button.rect().center())
    assert abs(center.x() - page.width() / 2) <= 2
    assert abs(center.y() - page.height() / 2) <= 2
    for mode in (ThemeMode.DARK, ThemeMode.LIGHT):
        page.theme_manager.set_mode(mode)
        assert page.enter_button.isVisible()
        assert not page.grab().isNull()


def test_assets_are_bundled_and_missing_assets_do_not_block_page(page, tmp_path):
    assert len(page.scene.cards) == 20
    assert all(not card.pixmap.isNull() for card in page.scene.cards)
    fallback = WelcomeScene(asset_directory=tmp_path)
    fallback.resize(640, 480)
    fallback.set_progress(1)
    fallback.show()
    APPLICATION.processEvents()
    assert not fallback.grab().isNull()
    fallback.close()


def test_error_restores_same_entry_button(page):
    page.finish_animation()
    page.enter_button.click()
    assert not page.enter_button.isEnabled()
    page.show_error("无法打开知识库，请检查配置后重试。")
    assert page.enter_button.isEnabled()
    assert page.enter_button.text() == "欢迎使用RAG系统"
    assert "重试" in page.feedback.text()
