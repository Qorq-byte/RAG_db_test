"""Global index maintenance independent of the selected knowledge collection."""

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtWidgets import QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ragdb.desktop.workers import BackgroundTask
from ragdb.domain.errors import ConflictError, StorageError


class IndexMaintenanceWidget(QWidget):
    def __init__(self, runtime) -> None:
        super().__init__()
        self.runtime = runtime
        self.inventory = None
        self._task = None
        self._success = None
        layout = QVBoxLayout(self)
        description = QLabel("查看所有知识集合的旧向量索引。条数表示向量数量，不代表可释放的磁盘字节数。")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.refresh_button = QPushButton("预览旧索引")
        self.refresh_button.setAccessibleName("预览所有知识集合的旧索引")
        layout.addWidget(self.refresh_button)
        self.feedback = QLabel("点击预览读取索引清单。")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.view = QTextBrowser()
        self.view.setAccessibleName("索引盘点结果")
        layout.addWidget(self.view)
        self.refresh_button.clicked.connect(self.refresh_preview)

    @property
    def busy(self):
        return self._task is not None

    def _run(self, function, success):
        if self.busy:
            return False
        self._success = success
        self.refresh_button.setEnabled(False)

        def safe_call():
            try:
                return function()
            except (ConflictError, StorageError) as exc:
                raise RuntimeError(str(exc)) from None
            except Exception:
                raise RuntimeError("索引操作失败，请检查配置和存储目录后重试。") from None

        task = BackgroundTask(None, safe_call)
        self._task = task
        task.signals.succeeded.connect(self._succeeded)
        task.signals.failed.connect(self._failed)
        task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(task)
        return True

    def refresh_preview(self):
        if self.busy:
            return
        self.inventory = None
        self.view.clear()
        self.feedback.setText("正在盘点索引…")
        self._run(lambda: self.runtime.index_maintenance_service().preview(), self.show_inventory)

    def show_inventory(self, inventory):
        self.inventory = inventory
        lines = [f"当前活动命名空间：{inventory.active_namespace}"]
        for state, title in (("active", "活动索引（保护）"), ("stale", "可清理的旧索引"), ("unknown", "需人工核查（保护）")):
            entries = [item for item in inventory.items if item.state == state]
            lines.extend(("", f"{title} · {len(entries)} 项"))
            for item in entries:
                lines.extend((f"{item.collection_name or '未知集合'} · {item.vector_count} 条向量",
                              item.name, item.reason))
        self.view.setPlainText("\n".join(lines))
        self.feedback.setText(f"预览完成：{len(inventory.candidates)} 项旧索引可清理。" if inventory.candidates else "没有可清理的旧索引。")

    @Slot(object, object)
    def _succeeded(self, _token, result):
        self._success(result)

    @Slot(object, str)
    def _failed(self, _token, message):
        self.inventory = None
        self.feedback.setText(message)

    @Slot(object)
    def _finished(self, _token):
        self._task = None
        self._success = None
        self.refresh_button.setEnabled(True)
