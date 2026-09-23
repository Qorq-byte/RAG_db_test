"""Task, audit log, and environment diagnostics page."""

from PySide6.QtWidgets import QPushButton, QTabWidget, QTextBrowser

from ragdb.desktop.study_pages import AsyncPage
from ragdb.diagnostics import run_diagnostics


class OperationsPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(
            runtime, "任务与诊断", "查看后台处理记录，并确认运行环境是否就绪。"
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
        self.set_content(tabs)
        refresh.clicked.connect(self.refresh)
        diagnose.clicked.connect(self.diagnose)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation)
        self.refresh()

    def refresh(self) -> None:
        if self.collection_id is None:
            self.tasks_view.setPlainText("请选择知识集合后查看任务记录。")
            self.logs_view.setPlainText("暂无可显示的操作日志。")
            return
        tasks = self.runtime.tasks.list_for_collection(self.collection_id)
        self.tasks_view.setPlainText(
            "\n".join(
                f"{item.started_at.isoformat()}  {item.status.value}  成功 {item.succeeded} / 失败 {item.failed}"
                for item in tasks
            )
            or "暂无任务。"
        )
        logs = self.runtime.operation_logs.list_recent(self.collection_id)
        self.logs_view.setPlainText(
            "\n".join(f"{item.created_at.isoformat()}  {item.action}" for item in logs)
            or "暂无操作日志。"
        )

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
