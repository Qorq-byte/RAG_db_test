"""Own the welcome-to-workbench handoff without blocking the intro animation."""

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QTimer, Slot
from PySide6.QtWidgets import QMainWindow

from ragdb.desktop.theme import ThemeManager
from ragdb.desktop.welcome import WelcomePage
from ragdb.desktop.workers import BackgroundTask


STARTUP_ERROR = "无法打开知识库。请检查配置文件、数据目录权限和系统凭据后重试。"


def _create_runtime():
    # Heavy storage/model imports are deferred until the user chooses to enter.
    from ragdb.runtime import ApplicationRuntime

    return ApplicationRuntime.from_config()


def _create_workbench(runtime, theme_manager):
    # Widgets must be constructed on the GUI thread.
    from ragdb.desktop.window import MainWindow

    return MainWindow(runtime, theme_manager)


class WelcomeWindow(QMainWindow):
    def __init__(
        self,
        theme_manager: ThemeManager,
        *,
        runtime_factory: Callable = _create_runtime,
        workbench_factory: Callable = _create_workbench,
        auth_page_factory: Callable | None = None,
        on_authenticated: Callable | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("RAG · 欢迎")
        self.resize(1280, 800)
        self.theme_manager = theme_manager
        self.page = WelcomePage(theme_manager, auth_at_end=auth_page_factory is not None)
        self.setCentralWidget(self.page)
        self.auth_page_factory = auth_page_factory
        self.on_authenticated = on_authenticated
        self.auth_page = None
        self.runtime_factory = runtime_factory
        self.workbench_factory = workbench_factory
        self.workbench = None
        self._task = None
        self._pending_runtime = None
        self._result_received = False
        self.page.enter_requested.connect(self._start)
        self.page.auth_requested.connect(self._show_auth)
        if auth_page_factory is not None and self.page.ready:
            QTimer.singleShot(0, self._show_auth)

    @Slot()
    def _show_auth(self) -> None:
        if self.auth_page is not None or self.auth_page_factory is None:
            return
        self.auth_page = self.auth_page_factory()
        self.auth_page.authenticated.connect(self._authenticated)
        self.setCentralWidget(self.auth_page)
        self.setWindowTitle("RAG DB · 登录 / 注册")

    @Slot(object)
    def _authenticated(self, session) -> None:
        if self.busy or self.workbench is not None:
            return
        if self.on_authenticated is not None:
            self.on_authenticated(session)
        self._start()

    @property
    def busy(self) -> bool:
        return self._task is not None

    @Slot()
    def _start(self) -> None:
        if self.busy or self.workbench is not None:
            return
        self._result_received = False
        self._pending_runtime = None

        def initialize():
            try:
                return self.runtime_factory()
            except Exception:
                # Configuration/provider exceptions may contain paths or secrets.
                raise RuntimeError(STARTUP_ERROR) from None

        self._task = BackgroundTask("startup", initialize)
        self._task.signals.succeeded.connect(self._runtime_ready)
        self._task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(self._task)

    @Slot(object, object)
    def _runtime_ready(self, _token, runtime) -> None:
        self._pending_runtime = runtime
        self._result_received = True

    @Slot(object)
    def _finished(self, _token) -> None:
        self._task = None
        if not self._result_received:
            (self.auth_page or self.page).show_error(STARTUP_ERROR)
            return
        runtime, self._pending_runtime = self._pending_runtime, None
        workbench = None
        try:
            workbench = self.workbench_factory(runtime, self.theme_manager)
            workbench.setGeometry(self.geometry())
            if self.isMaximized():
                workbench.showMaximized()
            else:
                workbench.show()
        except Exception:
            if workbench is not None:
                workbench.close()
                workbench.deleteLater()
            (self.auth_page or self.page).show_error(STARTUP_ERROR)
            return
        # Keep the new top-level window alive and show it before closing the last
        # visible welcome window, so Qt does not quit during the handoff.
        self.workbench = workbench
        self.close()

    def closeEvent(self, event) -> None:
        if self.busy:
            (self.auth_page or self.page).show_error("正在打开工作台，请等待完成后关闭。")
            event.ignore()
            return
        super().closeEvent(event)
