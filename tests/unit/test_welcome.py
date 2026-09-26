import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QAbstractAnimation, QSettings, Qt, QPoint, QPointF
from PySide6.QtTest import QTest
from PySide6.QtGui import QWheelEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from ragdb.desktop.theme import ThemeManager, ThemeMode
from ragdb.desktop.welcome import WelcomePage
from ragdb.desktop.welcome_scene import WelcomeScene, card_poses


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


def wait_until(predicate, timeout=10):
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
    assert not page.ready and not page.enter_button.isVisible()
    wheel(page, -3000)
    wait_until(lambda: page.ready)
    assert page.enter_button.isVisible()
    assert page.enter_button.text() == "欢迎使用RAG系统"
    assert not entered
    page.enter_button.click()
    page.enter_button.click()
    assert entered == [True]


def test_intro_stops_at_circle_and_waits_for_scroll(theme):
    widget = WelcomePage(theme, duration_ms=40)
    widget.show()
    try:
        wait_until(lambda: widget.scene.progress == 1)
        assert not widget.ready
        assert not widget.enter_button.isVisible()
    finally:
        widget.close()


def test_skip_only_reveals_button_and_keyboard_enters(page):
    entered = []
    page.enter_requested.connect(lambda: entered.append(True))
    QTest.keyClick(page, Qt.Key.Key_Escape)
    APPLICATION.processEvents()
    assert page.ready and not entered
    assert page.scene.virtual_scroll == 3000
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
    page.finish_intro()
    page.resize(*size)
    APPLICATION.processEvents()
    viewport = page.scene.sceneRect()
    page.scene._render(snap=True)
    assert all(viewport.contains(card.sceneBoundingRect()) for card in page.scene.cards)
    page.finish_animation()
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


def wheel(page, angle, pixel=0):
    view = page.scene.viewport()
    event = QWheelEvent(QPointF(view.rect().center()), QPointF(view.mapToGlobal(view.rect().center())),
                        QPoint(0, pixel), QPoint(0, angle), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view, event)


def test_wheel_morph_sweep_reverse_bounds_and_final_button(page):
    page.finish_intro()
    wheel(page, -600)
    wait_until(lambda: page.scene.settled)
    assert page.scene.values[:2] == [1, 0]
    assert not page.enter_button.isVisible()
    visible = lambda: {i for i, c in enumerate(page.scene.cards)
                       if page.scene.sceneRect().intersects(c.sceneBoundingRect())}
    arc_cards = visible()
    positions = [c.pos() for c in page.scene.cards]
    wheel(page, -1200)
    wait_until(lambda: page.scene.settled)
    assert page.scene.values[1] == .5
    assert any(c.pos() != p for c, p in zip(page.scene.cards, positions))
    assert arc_cards - visible()  # earlier cards have left the clipped viewport
    assert not page.ready
    wheel(page, -9000)
    wait_until(lambda: page.ready)
    assert page.scene.virtual_scroll == 3000
    wheel(page, 120)
    assert not page.ready and not page.enter_button.isVisible()
    wheel(page, 9000)
    wait_until(lambda: page.scene.settled)
    assert page.scene.virtual_scroll == 0
    assert page.scene.values[:2] == [0, 0]
    assert len(visible()) == 20


def test_precise_touchpad_and_mouse_parallax(page):
    page.finish_intro()
    wheel(page, -120, pixel=-25)
    assert page.scene.virtual_scroll == 25  # don't count angleDelta a second time
    wheel(page, 0, pixel=-575)
    wait_until(lambda: page.scene.settled)
    before = page.scene.cards[10].pos().x()
    view = page.scene.viewport()
    local = QPointF(view.width() - 2, view.height() / 2)
    event = QMouseEvent(QMouseEvent.Type.MouseMove, local, local,
                        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(view, event)
    wait_until(lambda: page.scene.settled)
    assert page.scene.cards[10].pos().x() > before + 90
    page.finish_animation()
    QApplication.sendEvent(view, event)
    assert page.ready  # pointer movement must not remove the final button


def test_reference_geometry_and_order_of_bottom_exit():
    poses = card_poses(1280, 800, 1, 1, 0, 0)
    assert poses[0].scale == 1.8
    assert min(p.y for p in poses) > 600
    # Track each card's bottom crossing during the bounded sweep, independently
    # of horizontal clipping. Later cards must cross later, not all fade at once.
    exits = []
    for i in range(10, 20):
        crossing = next(step for step in range(101)
                        if (pose := card_poses(1280, 800, 1, 1, step / 100)[i]).y > 800
                        and pose.x < 640)
        exits.append(crossing)
    assert exits == sorted(exits)
    assert len(set(exits)) == 10


def test_hidden_scene_stops_scroll_timer_and_resumes(page):
    page.finish_intro()
    wheel(page, -600)
    assert page.scene.timer.isActive()
    page.hide()
    assert not page.scene.timer.isActive()
    page.show()
    wait_until(lambda: page.scene.settled)
    assert not page.scene.timer.isActive()
    assert page.scene.values[0] == 1


def test_touch_swipe_and_hover_flip(page):
    page.finish_intro()
    page.scene._render(snap=True)
    view = page.scene.viewport()
    device = QTest.createTouchDevice()
    QTest.touchEvent(view, device).press(0, QPoint(600, 400), view).commit()
    QTest.touchEvent(view, device).move(0, QPoint(600, 100), view).commit()
    QTest.touchEvent(view, device).release(0, QPoint(600, 100), view).commit()
    APPLICATION.processEvents()
    assert page.scene.virtual_scroll == 300
    page.scene.scroll_by(-300)
    wait_until(lambda: page.scene.settled)
    card = page.scene.cards[0]
    point = page.scene.mapFromScene(card.scenePos())
    QTest.mouseMove(view, point)
    wait_until(lambda: card.flip_value >= .99)
    assert card.hovered
    QTest.mouseMove(view, QPoint(640, 400))
    wait_until(lambda: abs(card.flip_value) < .01)
    assert not card.hovered
