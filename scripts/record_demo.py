"""Record real Qt widgets with synthetic data, offline vectors and scripted chat.

Run from the repository: uv run python scripts/record_demo.py
Requires ffmpeg on PATH. No desktop capture, user configuration or API calls.
"""
import os
import subprocess
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
for key in list(os.environ):
    if key.startswith("RAGDB_"):
        del os.environ[key]

from PySide6.QtCore import QSettings, QThreadPool, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QTabWidget
from ragdb.config import AppSettings, AuthSettings
from ragdb.runtime import ApplicationRuntime
import ragdb.runtime as runtime_module
from ragdb.infrastructure.database import SQLiteDatabase
from ragdb.application.evaluation import OfflineEmbedding
from ragdb.desktop.theme import ThemeManager, ThemeMode
from ragdb.desktop.welcome import WelcomePage
from ragdb.desktop.auth_page import AuthPage
from ragdb.desktop.window import MainWindow


class DemoChat:
    provider_name = "demo"
    model_name = "scripted-answer"

    def stream(self, messages, *, should_cancel=None):
        answer = (
            "RAG 的基本流程是 **先检索，再生成**。[1]\n\n"
            "1. 导入资料后，系统解析文本、切分内容并建立检索索引。[1]\n"
            "2. 提问时，从当前知识集合检索相关片段。[1]\n"
            "3. 把片段作为依据交给问答模型，生成带来源编号的回答。[1]\n\n"
            "可以点击下方引用，核对答案与原始资料。"
        )
        for i in range(0, len(answer), 3):
            if should_cancel and should_cancel():
                return
            time.sleep(.065)
            yield answer[i:i + 3]


def main():
    root = Path(__file__).resolve().parents[1]
    media = root / "docs" / "media"
    media.mkdir(parents=True, exist_ok=True)
    review = root / ".data" / "readme-media-check"
    review.mkdir(parents=True, exist_ok=True)
    # A fresh directory prevents accidental access to the real library or .env.
    with tempfile.TemporaryDirectory(prefix="ragdb-public-demo-", dir=review,
                                     ignore_cleanup_errors=True) as directory:
        sandbox = Path(directory)
        os.chdir(sandbox)
        settings = AppSettings(_env_file=None, storage={"data_dir": sandbox / "data"})
        database = SQLiteDatabase(settings.storage.data_dir / "ragdb.sqlite3")
        database.initialize()
        runtime_module.create_embedding_provider = lambda _: OfflineEmbedding()
        runtime_module.create_chat_model = lambda _: DemoChat()
        runtime = ApplicationRuntime(settings, database, sandbox / "demo.toml")
        app = QApplication([])
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "seguisym.ttf"):
            path = fonts / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
        app.setFont(QFont("Microsoft YaHei UI", 10))
        theme = ThemeManager(QSettings(str(sandbox / "appearance.ini"), QSettings.Format.IniFormat))
        theme.set_mode(ThemeMode.LIGHT)
        welcome = WelcomePage(theme, auth_at_end=True)
        welcome.resize(1280, 800)
        welcome.show()
        auth_page = None
        window = None

        def show_auth():
            nonlocal auth_page
            auth_page = AuthPage(AuthSettings(), reduce_motion=True)
            auth_page.resize(1280, 800)
            auth_page.show()
            welcome.hide()

        def enter():
            nonlocal window
            window = MainWindow(runtime, theme)
            window.resize(1280, 800)
            window.show()
            auth_page.hide()

        welcome.auth_requested.connect(show_auth)
        ffmpeg = subprocess.Popen([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
            "-video_size", "1280x880", "-framerate", "12", "-i", "-", "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "24", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-map_metadata", "-1", str(media / "ragdb-tour.mp4")
        ], stdin=subprocess.PIPE)
        done = set()
        caption = "01 / 启动欢迎页：图片聚合，向下滚动探索"
        collection = None
        try:
            for frame in range(75 * 12):
                started = time.monotonic()
                t = frame / 12
                def once(at, key, operation):
                    if t >= at and key not in done:
                        operation()
                        done.add(key)
                if 5 <= t < 12:
                    welcome.scene.scroll_by(55)
                once(11.5, "entry-ready", welcome.finish_animation)
                if t >= 15 and "register" not in done:
                    assert auth_page is not None, "Welcome did not show the account page"
                    auth_page.register_tab.click()
                    caption = "02 / 邮箱注册：先获取验证码，再设置密码（画面为离线示意）"
                    done.add("register")
                if t >= 19 and "login" not in done:
                    auth_page.login_tab.click()
                    caption = "03 / 登录后进入工作台；演示不连接真实认证服务"
                    done.add("login")
                once(22, "enter", enter)
                if t >= 24 and "collection" not in done:
                    assert window is not None, "Welcome entry did not activate"
                    window.navigation.select_page(1)
                    collection = runtime.collection_service().create("RAG 入门 · 演示资料")
                    window.collections_page.refresh(selected_id=collection.id)
                    caption = "04 / 集合与资料：创建独立知识集合，导入学习文本"
                    done.add("collection")
                if t >= 28 and "import" not in done:
                    text = "RAG 的基本流程是先检索，再生成。导入资料后，系统解析文本、切分内容并建立检索索引。提问时，从当前知识集合检索相关片段，把片段作为依据交给问答模型，生成带来源编号的回答。"
                    window.collections_page._run(collection, lambda: runtime.ingestion_service().ingest_text(collection, text, "RAG 流程说明（演示）"), kind="text")
                    done.add("import")
                if t >= 35 and "search" not in done:
                    assert not window.collections_page._import_in_flight
                    assert window.collections_page.sources.rowCount() == 1
                    window.navigation.select_page(2)
                    search = window.pages.widget(2)
                    search.query.setText("RAG 的基本流程")
                    search.search_button.click()
                    caption = "05 / 检索：定位相关片段，点击结果核对原始证据"
                    done.add("search")
                if t >= 39 and "hit" not in done:
                    assert search.results.count() > 0
                    search.results.setCurrentRow(0)
                    done.add("hit")
                if t >= 43 and "chat" not in done:
                    window.navigation.select_page(3)
                    window.close_detail_preference()
                    window.chat_page.question.setPlainText("RAG 的基本流程是什么？")
                    caption = "06 / 问答：先核对当前提问集合，再发送问题"
                    done.add("chat")
                once(45, "ask", lambda: window.chat_page.ask_button.click())
                if 47 <= t < 57:
                    caption = "07 / 实时回答：问题在右，回答在左，查看进度与引用"
                if t >= 57 and "tasks" not in done:
                    assert not window.chat_page.busy
                    assert len(runtime.conversations.list_for_collection(collection.id)) == 1
                    window.navigation.select_page(5)
                    caption = "08 / 任务与诊断：查看导入任务与操作日志"
                    done.add("tasks")
                once(60, "logs", lambda: window.operations_page.findChild(QTabWidget).setCurrentIndex(1))
                if t >= 64 and "overview" not in done:
                    window.navigation.select_page(0)
                    caption = "09 / 返回概览：资料、会话与任务数量同步更新"
                    done.add("overview")
                if t >= 69 and "model" not in done:
                    window.model_action.trigger()
                    caption = "10 / 左上角个人菜单：进入模型配置页面"
                    done.add("model")
                app.processEvents()
                widget = window or auth_page or welcome
                canvas = QImage(1280, 880, QImage.Format.Format_RGB888)
                canvas.fill(QColor("#101827"))
                painter = QPainter(canvas)
                snapshot = widget.grab().scaled(1280, 800, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap((1280 - snapshot.width()) // 2,
                                   (800 - snapshot.height()) // 2, snapshot)
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Microsoft YaHei UI", 14))
                painter.drawText(24, 831, caption)
                painter.setPen(QColor("#bdc8db"))
                painter.setFont(QFont("Microsoft YaHei UI", 10))
                painter.drawText(24, 860, "RAGDB 桌面演示 · 真实界面 / 模拟认证 / 虚构资料 / 离线向量 / 模拟回答")
                painter.end()
                ffmpeg.stdin.write(bytes(canvas.bits()))
                if frame in (48, 216, 576, 816):
                    canvas.save(str(review / f"tour-{frame // 12:02d}.png"))
                if frame == 576:
                    canvas.save(str(media / "ragdb-tour-poster.png"))
                time.sleep(max(0, 1 / 12 - (time.monotonic() - started)))
        finally:
            ffmpeg.stdin.close()
            result = ffmpeg.wait(timeout=30)
            QThreadPool.globalInstance().waitForDone(30000)
            if window:
                window.close()
            if auth_page:
                auth_page.close()
            welcome.close()
            app.processEvents()
            os.chdir(root)
        assert result == 0
        assert {"register", "login", "overview", "model"} <= done
        print("PASS: recorded 75 seconds; account screen, import, search, chat and navigation verified")


if __name__ == "__main__":
    main()
