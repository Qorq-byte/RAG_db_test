"""Desktop application entry point."""

import sys
import os
from pathlib import Path
import argparse

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from ragdb.auth import AuthService, account_settings
from ragdb.config import load_settings
from ragdb.desktop.auth_dialog import AuthDialog
from ragdb.desktop.startup import WelcomeWindow
from ragdb.desktop.theme import ThemeManager
from ragdb.desktop.workers import BackgroundTask


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 知识库桌面工作台")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    options, _ = parser.parse_known_args()
    application = QApplication.instance() or QApplication(sys.argv)
    theme_manager = ThemeManager()
    theme_manager.apply()
    exit_after_ms = os.environ.get("RAGDB_GUI_TEST_EXIT_MS")
    settings = load_settings(config_path=options.config)
    application.setQuitOnLastWindowClosed(False)
    while True:
        dialog = AuthDialog(settings.auth)
        if exit_after_ms:
            # The smoke timer must end the dialog's nested event loop too.
            QTimer.singleShot(
                int(exit_after_ms),
                lambda: dialog.done(QDialog.DialogCode.Rejected) if dialog.isVisible() else application.quit(),
            )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.session is None:
            return 0
        account = account_settings(settings, dialog.session.user_id)
        state = {"again": False, "session": dialog.session, "task": None}

        def create_runtime():
            from ragdb.runtime import ApplicationRuntime

            auth = AuthService(settings.auth)
            try:
                verified = auth.restore()
            finally:
                auth.close()
            if verified.user_id != state["session"].user_id:
                raise RuntimeError("登录账号已变更，请重新打开工作台。")
            state["session"] = verified
            return ApplicationRuntime.from_config(options.config, settings=account)

        def create_workbench(runtime, manager):
            from ragdb.desktop.window import MainWindow

            workbench = MainWindow(runtime, manager)
            session_timer = QTimer(workbench)
            session_timer.setInterval(5 * 60 * 1000)

            def verify_session():
                if state["task"] is not None:
                    return

                def refresh():
                    auth = AuthService(settings.auth)
                    try:
                        verified = auth.restore()
                    finally:
                        auth.close()
                    if verified.user_id != state["session"].user_id:
                        raise RuntimeError("登录账号已变更。")
                    return verified

                task = BackgroundTask("verify", refresh)
                state["task"] = task
                task.signals.succeeded.connect(lambda _token, verified: state.update(session=verified))
                task.signals.failed.connect(
                    lambda _token, _error: (
                        state.update(again=True),
                        session_timer.stop(),
                        workbench.close(),
                        application.quit(),
                    )
                )
                task.signals.finished.connect(lambda _token: state.update(task=None))
                QThreadPool.globalInstance().start(task)

            session_timer.timeout.connect(verify_session)
            session_timer.start()

            def finish_logout(_token=None):
                state["task"] = None
                state["again"] = True
                session_timer.stop()
                workbench.close()
                application.quit()

            def logout():
                if state["task"] is not None:
                    return
                session_timer.stop()
                workbench.logout_button.setEnabled(False)
                workbench.statusBar().showMessage("正在退出登录…")

                def sign_out():
                    auth = AuthService(settings.auth)
                    try:
                        auth.sign_out(state["session"])
                    finally:
                        auth.close()

                task = BackgroundTask("logout", sign_out)
                state["task"] = task
                task.signals.succeeded.connect(finish_logout)
                task.signals.failed.connect(
                    lambda _token, error: (
                        workbench.statusBar().showMessage(error),
                        workbench.logout_button.setEnabled(True),
                        session_timer.start(),
                    )
                )
                task.signals.finished.connect(lambda _token: state.update(task=None))
                QThreadPool.globalInstance().start(task)

            workbench.logout_requested.connect(logout)
            return workbench

        window = WelcomeWindow(
            theme_manager, runtime_factory=create_runtime,
            workbench_factory=create_workbench,
        )
        window.show()
        application.setQuitOnLastWindowClosed(True)
        result = application.exec()
        application.setQuitOnLastWindowClosed(False)
        if not state["again"]:
            return result


if __name__ == "__main__":
    raise SystemExit(main())
