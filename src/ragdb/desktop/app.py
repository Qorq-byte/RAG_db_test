"""Desktop application entry point."""

import sys
import os
from pathlib import Path
import argparse

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from ragdb.auth import AuthService, account_settings, delete_local_account_data
from ragdb.config import load_settings
from ragdb.desktop.auth_page import AuthPage
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
        state = {"again": False, "session": None, "task": None}

        def accepted(session):
            state["session"] = session

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
            return ApplicationRuntime.from_config(
                options.config, settings=account_settings(settings, verified.user_id)
            )

        def create_workbench(runtime, manager):
            from ragdb.desktop.window import MainWindow

            workbench = MainWindow(runtime, manager, session=state["session"])
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

            def delete_account(code: str):
                if state["task"] is not None:
                    workbench.statusBar().showMessage("请等待当前账号操作完成后再注销。")
                    return
                session_timer.stop()
                application.setQuitOnLastWindowClosed(False)
                if not workbench.close():
                    application.setQuitOnLastWindowClosed(True)
                    session_timer.start()
                    workbench.statusBar().showMessage("请先结束正在进行的任务，再注销账号。")
                    return

                def remove():
                    auth = AuthService(settings.auth)
                    try:
                        verified = auth.restore()
                        if verified.user_id != state["session"].user_id:
                            raise RuntimeError("登录账号已变更，请重新登录后重试。")
                        auth.delete_account(verified, code)
                        warnings = []
                        try:
                            auth.sign_out()
                        except Exception:
                            warnings.append("本机登录凭据未能清除，请在系统凭据库中手工移除。")
                    finally:
                        auth.close()
                    try:
                        delete_local_account_data(settings.storage.data_dir, verified.user_id)
                    except OSError:
                        warnings.append("本机账号资料未能完全删除，请手工检查该账号的数据目录。")
                    return warnings

                task = BackgroundTask("delete-account", remove)
                state["task"] = task

                def completed(_token, warnings):
                    state["again"] = True
                    if warnings:
                        QMessageBox.warning(None, "账号已删除", "服务端账号已删除。" + " ".join(warnings))
                    application.quit()

                def failed(_token, error):
                    workbench.show()
                    application.setQuitOnLastWindowClosed(True)
                    session_timer.start()
                    workbench.statusBar().showMessage(error)

                task.signals.succeeded.connect(completed)
                task.signals.failed.connect(failed)
                task.signals.finished.connect(lambda _token: state.update(task=None))
                QThreadPool.globalInstance().start(task)

            workbench.account_deletion_requested.connect(delete_account)
            return workbench

        window = WelcomeWindow(
            theme_manager, runtime_factory=create_runtime,
            workbench_factory=create_workbench,
            auth_page_factory=lambda: AuthPage(
                settings.auth, reduce_motion=theme_manager.reduce_motion
            ),
            on_authenticated=accepted,
        )
        window.show()
        if exit_after_ms:
            QTimer.singleShot(int(exit_after_ms), application.quit)
        application.setQuitOnLastWindowClosed(True)
        result = application.exec()
        application.setQuitOnLastWindowClosed(False)
        if not state["again"]:
            return result


if __name__ == "__main__":
    raise SystemExit(main())
