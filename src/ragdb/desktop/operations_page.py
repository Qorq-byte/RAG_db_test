"""Task, audit log, and environment diagnostics page."""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

from ragdb.desktop.study_pages import AsyncPage
from ragdb.diagnostics import run_diagnostics


class OperationsPage(AsyncPage):
    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("任务与诊断"))
        buttons = QHBoxLayout()
        refresh = QPushButton("刷新任务与日志")
        diagnose = QPushButton("运行诊断")
        buttons.addWidget(refresh); buttons.addWidget(diagnose); buttons.addStretch(); layout.addLayout(buttons)
        self.tasks_view = QTextBrowser(); self.logs_view = QTextBrowser(); self.diagnostics_view = QTextBrowser()
        layout.addWidget(QLabel("最近任务")); layout.addWidget(self.tasks_view)
        layout.addWidget(QLabel("操作日志")); layout.addWidget(self.logs_view)
        layout.addWidget(QLabel("环境诊断")); layout.addWidget(self.diagnostics_view)
        refresh.clicked.connect(self.refresh)
        diagnose.clicked.connect(self.diagnose)

    def set_collection(self, collection_id, name: str, generation: int) -> None:
        super().set_collection(collection_id, name, generation)
        self.refresh()

    def refresh(self) -> None:
        if self.collection_id is None:
            self.tasks_view.setPlainText("请选择知识集合。")
            self.logs_view.clear()
            return
        tasks = self.runtime.tasks.list_for_collection(self.collection_id)
        self.tasks_view.setPlainText("\n".join(f"{item.started_at.isoformat()}  {item.status.value}  成功 {item.succeeded} / 失败 {item.failed}" for item in tasks) or "暂无任务。")
        logs = self.runtime.operation_logs.list_recent(self.collection_id)
        self.logs_view.setPlainText("\n".join(f"{item.created_at.isoformat()}  {item.action}" for item in logs) or "暂无操作日志。")

    def diagnose(self) -> None:
        self.diagnostics_view.setPlainText("正在诊断…")
        self.run_task(lambda: run_diagnostics(self.runtime.config_path), self.show_diagnostics)

    def show_diagnostics(self, results) -> None:
        self.diagnostics_view.setPlainText("\n".join(f"[{item.status.value}] {item.name}：{item.detail}" for item in results))
