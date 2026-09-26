"""Background library backup and non-destructive restore controls."""

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from ragdb.application.backup import BackupService
from ragdb.desktop.workers import BackgroundTask


class BackupWidget(QWidget):
    def __init__(self, runtime):
        super().__init__()
        self.runtime = runtime
        self._task = None
        layout = QVBoxLayout(self)
        description = QLabel("备份全部集合、已入库正文、向量、对话、学习产物和配置。密钥和库外原文件不包含。恢复到新目录，不覆盖当前库。")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.create_button = QPushButton("创建全库备份")
        self.verify_button = QPushButton("校验备份")
        self.restore_button = QPushButton("恢复到新目录")
        self.buttons = [self.create_button, self.verify_button, self.restore_button]
        for button in self.buttons:
            layout.addWidget(button)
        self.feedback = QLabel("请选择操作。恢复后可使用生成的配置启动知识库。")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        layout.addStretch()
        self.create_button.clicked.connect(self.create_backup)
        self.verify_button.clicked.connect(self.verify_backup)
        self.restore_button.clicked.connect(self.restore_backup)

    @property
    def busy(self):
        return self._task is not None

    def _run(self, function, message):
        if self.busy:
            return
        for button in self.buttons:
            button.setEnabled(False)
        self.feedback.setText("正在处理，请等待完成…")
        task = BackgroundTask(None, function)
        self._task = task
        task.signals.succeeded.connect(lambda _token, result: self.feedback.setText(message(result)))
        task.signals.failed.connect(lambda _token, error: self.feedback.setText(f"操作失败：{error}"))
        task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(task)

    def _finished(self, _token):
        self._task = None
        for button in self.buttons:
            button.setEnabled(True)

    def create_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "创建全库备份", "ragdb-backup.zip", "ZIP (*.zip)")
        if path:
            self._run(lambda: BackupService(self.runtime.settings).create(Path(path)),
                      lambda result: f"备份完成：{result['path']}\nSHA256：{result['sha256']}")

    def verify_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "校验备份", "", "ZIP (*.zip)")
        if path:
            self._run(lambda: BackupService.verify(Path(path)),
                      lambda result: f"校验通过，共 {result['collections']} 个向量集合。")

    def restore_backup(self):
        archive, _ = QFileDialog.getOpenFileName(self, "选择备份", "", "ZIP (*.zip)")
        if not archive:
            return
        parent = QFileDialog.getExistingDirectory(self, "选择恢复目录的父目录")
        if parent:
            from PySide6.QtWidgets import QInputDialog
            name, accepted = QInputDialog.getText(self, "新目录名称", "输入尚不存在的目录名：", text="ragdb-restored")
            if accepted and name and Path(name).name == name and not any(c in name for c in "/\\:"):
                self._run(lambda: BackupService.restore(Path(archive), Path(parent) / name),
                          lambda result: f"恢复完成，当前库未变。\n配置：{result}\n启动：ragdb-gui --config \"{result}\"")
