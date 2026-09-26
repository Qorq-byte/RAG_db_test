import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from time import monotonic
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from ragdb.desktop.theme import LIGHT, build_stylesheet
from ragdb.desktop.wet_paint import install_wet_paint

APP = QApplication.instance() or QApplication([])

@pytest.fixture
def paint_ui():
    old_style = APP.styleSheet()
    APP.setStyleSheet(build_stylesheet(LIGHT))
    window = QWidget()
    window.resize(400, 230)
    button = QPushButton('Wet paint', window)
    button.setGeometry(100, 60, 180, 44)
    window.show()
    APP.processEvents()
    control = install_wet_paint(APP)
    control.clear()
    yield window, button, control
    control.set_reduce_motion(True)
    window.close()
    window.deleteLater()
    APP.processEvents()
    APP.setStyleSheet(old_style)

def move(window, point):
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point), QPointF(window.mapToGlobal(point)),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(window, event)

def test_only_near_pointer_starts_and_leaving_stops(paint_ui):
    window, button, control = paint_ui
    assert not control.timer.isActive()
    move(window, QPoint(80, 80))
    assert not control.timer.isActive()
    move(window, QPoint(85, 80))
    assert control.active_button is button
    assert control.timer.isActive()
    control.started = monotonic() - 1
    active = window.grab().toImage()
    move(window, QPoint(20, 200))
    assert control.active_button is None
    assert not control.timer.isActive()
    idle = window.grab().toImage()
    assert active.pixelColor(121, 111) != idle.pixelColor(121, 111)

def test_overlay_does_not_intercept_clicks_or_change_focus(paint_ui):
    window, button, control = paint_ui
    clicked = []
    button.clicked.connect(lambda: clicked.append(True))
    move(window, QPoint(150, 80))
    assert control.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert clicked == [True]
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert clicked == [True, True]

@pytest.mark.parametrize('state', ['disabled', 'hidden', 'reduce_motion', 'excluded'])
def test_ineligible_buttons_do_not_animate(paint_ui, state):
    window, button, control = paint_ui
    if state == 'disabled': button.setEnabled(False)
    elif state == 'hidden': button.hide()
    elif state == 'reduce_motion': control.set_reduce_motion(True)
    else: button.setProperty('wetPaintDisabled', True)
    move(window, QPoint(150, 80))
    assert not control.timer.isActive()

def test_disabling_active_button_stops_animation(paint_ui):
    window, button, control = paint_ui
    move(window, QPoint(150, 80))
    button.setEnabled(False)
    assert not control.timer.isActive()
    assert not control.overlay.isVisible()
