import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QAbstractAnimation, QSettings, Qt, QPoint, QPointF
from PySide6.QtGui import QPalette, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ragdb.desktop.sidebar_fan import ASSETS, FanCarousel, fan_pose
from ragdb.desktop.theme import ThemeManager, ThemeMode
from ragdb.desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])


def wait_for(predicate):
    end = time.monotonic() + 4
    while not predicate() and time.monotonic() < end:
        APP.processEvents()
        QTest.qWait(5)
    assert predicate()


@pytest.fixture
def fan():
    widget = FanCarousel()
    widget.resize(212, 240)
    widget.show()
    APP.processEvents()
    yield widget
    widget.close()
    APP.processEvents()


def test_staggered_entry_and_pagination_lock(fan):
    canvas = fan.canvas
    assert canvas.busy
    wheel(fan.canvas, -120)
    assert canvas.center == 3
    assert canvas.animation.duration() == 1760
    assert canvas.count == 10
    assert all(not photo.isNull() for photo in canvas.photos)
    wait_for(lambda: not canvas.busy)
    assert sum(p.opacity > .99 for p in canvas.poses) == 7
    assert canvas.visible_map() == {i: i for i in range(7)}
    wheel(fan.canvas, -120)
    assert canvas.center == 4 and canvas.busy
    wheel(fan.canvas, -120)
    assert canvas.center == 4
    wait_for(lambda: not canvas.busy)
    assert set(canvas.visible_map()) == set(range(1, 8))
    assert canvas.poses[0].opacity == 0
    assert canvas.poses[7].opacity == 1


def test_hover_lifts_card_pushes_neighbors_and_restores_on_leave(fan):
    c = fan.canvas
    wait_for(lambda: not c.busy)
    before = list(c.poses)
    # Hit the center card through real widget mouse input.
    point = c.hit_paths[3].boundingRect().center().toPoint()
    QTest.mouseMove(c, point)
    wait_for(lambda: c.active_slot == 3 and c.animation.state() == QAbstractAnimation.State.Stopped)
    assert c.poses[3].y < before[3].y
    assert c.poses[3].scale == pytest.approx(1.08)
    assert c.poses[2].x < before[2].x and c.poses[4].x > before[4].x
    QTest.mouseMove(fan, QPoint(0, fan.height() - 1))
    wait_for(lambda: c.active_slot is None and c.animation.state() == QAbstractAnimation.State.Stopped)
    assert c.poses == before


def test_cycle_wraps_keyboard_and_reduced_motion(fan):
    c = fan.canvas
    c.set_reduce_motion(True)
    for _ in range(7):
        QTest.keyClick(c, Qt.Key.Key_Right)
    assert c.center == 0
    assert set(c.visible_map()) == {7, 8, 9, 0, 1, 2, 3}
    QTest.keyClick(c, Qt.Key.Key_Left)
    assert c.center == 9
    assert not c.busy
    assert c.animation.state() == QAbstractAnimation.State.Stopped
    assert "10" in fan.dots.accessibleDescription()


def test_hidden_widget_stops_motion_and_restores_final_fan(fan):
    fan.hide()
    c = fan.canvas
    assert c.animation.state() == QAbstractAnimation.State.Stopped
    assert not c.leave_timer.isActive()
    fan.show()
    wait_for(lambda: not c.busy)
    wheel(fan.canvas, -120)
    fan.hide()
    assert not c.busy and c.animation.state() == QAbstractAnimation.State.Stopped
    fan.show()
    APP.processEvents()
    assert sum(p.opacity == 1 for p in c.poses) == 7


@pytest.mark.parametrize("width,height", [(136, 130), (212, 240), (376, 300)])
def test_fan_fits_sidebar_and_controls_remain_usable(fan, width, height):
    fan.canvas.set_reduce_motion(True)
    fan.resize(width, height)
    APP.processEvents()
    fan.grab()
    for path in fan.canvas.hit_paths.values():
        assert fan.canvas.rect().contains(path.boundingRect().toAlignedRect())
    assert fan.dots.isVisible() and fan.scroll_hint.isVisible()
    assert fan.rect().contains(fan.scroll_hint.geometry())


def test_remove_add_preference_survives_restart_and_collapse(tmp_path):
    ini = tmp_path / "ui.ini"
    manager = ThemeManager(QSettings(str(ini), QSettings.Format.IniFormat))
    manager.set_reduce_motion(True)
    window = MainWindow(theme_manager=manager)
    window.show()
    APP.processEvents()
    nav = window.navigation
    assert nav.footer.isVisible()
    nav.footer_toggle.click()
    assert not nav.footer.isVisible()
    assert nav.footer_toggle.text() == "添加底部卡片"
    assert not manager.sidebar_footer_visible()
    window.close()
    reloaded = ThemeManager(QSettings(str(ini), QSettings.Format.IniFormat))
    other = MainWindow(theme_manager=reloaded)
    other.show()
    APP.processEvents()
    try:
        nav = other.navigation
        assert not nav.footer_visible
        nav.footer_toggle.click()
        assert nav.footer.isVisible() and reloaded.sidebar_footer_visible()
        nav.set_collapsed(True)
        assert not nav.footer.isVisible()
        assert reloaded.sidebar_footer_visible()
        nav.set_collapsed(False)
        assert nav.footer.isVisible()
        reloaded.set_mode(ThemeMode.DARK)
        assert nav.footer.palette().color(QPalette.ColorRole.WindowText).name() == "#e8edf4"
        nav.select_page(2)
        assert other.pages.currentIndex() == 2
    finally:
        other.close()
        APP.setStyleSheet("")


@pytest.mark.parametrize("count", [0, 1, 5, 7])
def test_small_collections_and_missing_photos(tmp_path, count):
    manifest = [{"file": f"{i}.jpg", "alt": f"Card {i}"} for i in range(count)]
    (tmp_path / "sources.json").write_text(json.dumps(manifest), encoding="utf-8")
    widget = FanCarousel(assets=tmp_path, reduce_motion=True)
    widget.resize(212, 240)
    widget.show()
    APP.processEvents()
    try:
        assert not widget.scroll_hint.isVisible()
        center = widget.canvas.center
        widget.canvas.cycle(1)
        assert widget.canvas.center == center
        assert not widget.grab().isNull()
        assert len(widget.canvas.visible_map()) == count
    finally:
        widget.close()


def test_short_sidebar_keeps_restore_control_without_useless_arrows(fan):
    fan.resize(136, 57)
    APP.processEvents()
    assert fan.compact_hint.isVisible()
    assert not fan.canvas.isVisible()
    assert not fan.scroll_hint.isVisible()
    assert fan.canvas.animation.state() == QAbstractAnimation.State.Stopped
    fan.resize(136, 170)
    APP.processEvents()
    assert not fan.compact_hint.isVisible()
    assert fan.canvas.isVisible() and fan.scroll_hint.isVisible()


def wheel(widget, angle=0, pixel=0, horizontal=False):
    event = QWheelEvent(QPointF(widget.rect().center()), QPointF(),
                       QPoint(pixel, 0) if horizontal else QPoint(0, pixel),
                       QPoint(0, angle), Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    APP.sendEvent(widget, event)
    assert event.isAccepted()


def test_wheel_direction_precision_and_no_extra_queued_pages(fan):
    c = fan.canvas
    wait_for(lambda: not c.busy)
    wheel(c, -120)
    assert c.center == 4
    for _ in range(10):
        wheel(c, -120)
    wait_for(lambda: not c.busy)
    assert c.center == 4  # input during transition must not queue delayed flips
    wheel(c, 120)
    wait_for(lambda: not c.busy)
    assert c.center == 3
    c.set_reduce_motion(True)
    wheel(c, -120, pixel=-10)
    assert c.center == 3  # pixel delta wins, no double count
    for _ in range(3):
        wheel(c, pixel=-10)
    assert c.center == 4
    wheel(c, pixel=40, horizontal=True)
    assert c.center == 3
    wheel(fan, -120)  # scrolling over the hint/dots also works
    assert c.center == 4


def test_partial_wheel_gesture_does_not_leak_across_hide(fan):
    c = fan.canvas
    c.set_reduce_motion(True)
    wheel(c, pixel=-30)
    fan.hide()
    fan.show()
    APP.processEvents()
    wheel(c, pixel=-10)
    assert c.center == 3
