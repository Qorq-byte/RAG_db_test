"""Background task primitives that keep Qt's event loop responsive."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class TaskSignals(QObject):
    succeeded = Signal(object, object)
    failed = Signal(object, str)
    finished = Signal(object)


class BackgroundTask(QRunnable):
    def __init__(self, context_token: object, function: Callable[[], Any]) -> None:
        super().__init__()
        self.context_token = context_token
        self.function = function
        self.signals = TaskSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as error:
            self.signals.failed.emit(self.context_token, str(error))
        else:
            self.signals.succeeded.emit(self.context_token, result)
        finally:
            self.signals.finished.emit(self.context_token)
