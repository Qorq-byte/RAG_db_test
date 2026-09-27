"""Task, audit log, and environment diagnostics page."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPushButton, QTabWidget, QTextBrowser

from ragdb.desktop.study_pages import AsyncPage
from ragdb.diagnostics import run_diagnostics
from ragdb.desktop.index_maintenance_widget import IndexMaintenanceWidget
from ragdb.desktop.backup_widget import BackupWidget
from ragdb.desktop.import_feedback import IMPORT_LABELS, TASK_LABELS, format_counts


class OperationsPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(
            runtime, "任务与诊断", "查看当前集合最近 20 条任务和操作记录；页面打开时每 2 秒自动刷新。"
        )
        refresh = QPushButton("刷新记录")
        diagnose = QPushButton("运行诊断")
        diagnose.setProperty("primary", True)
        self.actions.addWidget(refresh)
        self.actions.addWidget(diagnose)
        tabs = QTabWidget()
        self.tasks_view = QTextBrowser()
        self.logs_view = QTextBrowser()
        self.diagnostics_view = QTextBrowser()
        tabs.addTab(self.tasks_view, "最近任务")
        tabs.addTab(self.logs_view, "操作日志")
        tabs.addTab(self.diagnostics_view, "环境诊断")
        self.index_maintenance = IndexMaintenanceWidget(runtime)
        tabs.addTab(self.index_maintenance, "索引维护")
        self.backup = BackupWidget(runtime)
        tabs.addTab(self.backup, "备份与恢复")
        self.set_content(tabs)
        refresh.clicked.connect(self.refresh)
        diagnose.clicked.connect(self.diagnose)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self.refresh_timer.start()

    def hideEvent(self, event) -> None:
        self.refresh_timer.stop()
        super().hideEvent(event)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation)
        self.refresh()

    def refresh(self) -> None:
        if self.collection_id is None:
            self.tasks_view.setPlainText("请选择知识集合后查看任务记录。")
            self.logs_view.setPlainText("请选择知识集合后查看操作日志。")
            return
        try:
            tasks = self.runtime.tasks.list_for_collection(self.collection_id)
            text = "\n\n".join(
                f"{item.started_at.astimezone():%Y-%m-%d %H:%M:%S}  "
                f"{TASK_LABELS.get(item.status.value, item.status.value)}  [任务 {str(item.id)[:8]}]\n"
                f"{format_counts(item.model_dump())}"
                for item in tasks
            ) or "当前集合暂无任务。导入资料后会自动显示处理记录。"
        except Exception:
            text = "读取任务记录失败，请检查数据目录是否可访问，再点击“刷新记录”。"
        self._update_text(self.tasks_view, text)
        try:
            logs = self.runtime.operation_logs.list_recent(self.collection_id)
            text = "\n\n".join(self._format_log(item) for item in logs) or "当前集合暂无操作日志。"
        except Exception:
            text = "读取操作日志失败，请检查数据目录是否可访问，再点击“刷新记录”。"
        self._update_text(self.logs_view, text)

    @staticmethod
    def _update_text(view, text) -> None:
        # Polling unchanged records must not reset a user's selection or scroll.
        if view.toPlainText() != text:
            scroll = view.verticalScrollBar().value()
            view.setPlainText(text)
            view.verticalScrollBar().setValue(scroll)

    @staticmethod
    def _format_log(item) -> str:
        prefix = f"{item.created_at.astimezone():%Y-%m-%d %H:%M:%S}  "
        details = item.details
        if item.action in ("import_started", "import_finished"):
            kind = IMPORT_LABELS.get(details.get("kind"), "资料导入")
            status = TASK_LABELS.get(details.get("status"), "未知状态")
            task_id = str(details.get("task_id", ""))[:8]
            return f"{prefix}{kind} · {status}  [任务 {task_id}]\n{format_counts(details)}"
        labels = {"source_ingested": "资料已导入", "directory_ingested": "目录已导入"}
        return prefix + labels.get(item.action, item.action)

    def diagnose(self) -> None:
        self.diagnostics_view.setPlainText("正在检查配置、数据库和模型连接…")
        self.run_task(
            lambda: run_diagnostics(self.runtime.config_path), self.show_diagnostics
        )

    def show_diagnostics(self, results) -> None:
        self.diagnostics_view.setPlainText(
            "\n".join(
                f"[{item.status.value}] {item.name}：{item.detail}" for item in results
            )
        )
