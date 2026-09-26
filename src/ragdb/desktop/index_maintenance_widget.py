"""Global index maintenance independent of the selected knowledge collection."""

from PySide6.QtCore import QThreadPool, Slot
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget

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
        self.clean_button = QPushButton("清理预览中的旧索引")
        self.clean_button.setEnabled(False)
        self.clean_button.setAccessibleName("确认并清理预览中的旧索引")
        layout.addWidget(self.clean_button)
        self.feedback = QLabel("点击预览读取索引清单。")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.view = QTextBrowser()
        self.view.setAccessibleName("索引盘点结果")
        layout.addWidget(self.view)
        self.refresh_button.clicked.connect(self.refresh_preview)
        self.clean_button.clicked.connect(self.clean_preview)

    @property
    def busy(self):
        return self._task is not None

    def _run(self, function, success):
        if self.busy:
            return False
        self._success = success
        self.refresh_button.setEnabled(False)
        self.clean_button.setEnabled(False)

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

    def confirm_cleanup(self, inventory):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("确认清理旧索引")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(f"将永久清理 {len(inventory.candidates)} 项旧索引。当前活动索引受保护。")
        dialog.setInformativeText("旧模型需要重新生成向量才能再次使用。请核对预览清单；展开详细信息可查看精确目标。")
        dialog.setDetailedText("\n".join(f"{item.name} · {item.vector_count} 条向量" for item in inventory.candidates))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def clean_preview(self):
        if self.busy or self.inventory is None or not self.inventory.candidates:
            return
        inventory = self.inventory
        if not self.confirm_cleanup(inventory):
            return
        self.inventory = None
        self.feedback.setText("正在清理旧索引；导入、删除和重建暂时互斥，请等待完成。")
        self._run(lambda: self.runtime.index_maintenance_service().clean(inventory.preview_id), self.show_cleanup)

    def show_cleanup(self, result):
        self.inventory = None
        lines = [f"已清理 {len(result.deleted)} 项；未清理 {len(result.remaining)} 项。"]
        lines.extend(f"已清理：{name}" for name in result.deleted)
        lines.extend(f"未清理：{name}" for name in result.remaining)
        for message in (result.error, result.audit_warning):
            if message:
                lines.append(message)
        self.view.setPlainText("\n".join(lines))
        self.feedback.setText("清理未全部完成，请重新预览后重试。" if result.error else
                              "清理完成，但日志记录失败；请保留结果并重新预览核对。" if result.audit_warning else
                              "清理完成。再次预览可核对剩余索引。")

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
        self.clean_button.setEnabled(bool(self.inventory and self.inventory.candidates))
