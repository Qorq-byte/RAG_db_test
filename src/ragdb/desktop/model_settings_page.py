"""Desktop model configuration, connection tests and safe embedding switching."""

from threading import Event

from PySide6.QtCore import QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from ragdb.application.embedding_rebuild import EmbeddingRebuildCancelled
from ragdb.application.model_settings import ModelSettingsService, chat_credential_name
from ragdb.config import load_settings
from ragdb.desktop.components import PageShell
from ragdb.desktop.workers import BackgroundTask
from ragdb.infrastructure.database.repository import embedding_profile_fingerprint


def label(text):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def model_caption(settings):
    name = settings.local_model if settings.provider == "local" else settings.cloud_model
    return f"{'本地' if settings.provider == 'local' else '云端'} · {name}"


class ModelForm(QFrame):
    changed = Signal()

    def __init__(self, section, settings, sources):
        super().__init__()
        self.section, self.base, self.sources = section, settings, sources
        self.setProperty("card", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = label("问答与生成" if section == "chat" else "嵌入模型")
        title.setProperty("resultTitle", True)
        layout.addWidget(title)
        layout.addWidget(label("用于问答、摘要和学习产物。" if section == "chat" else "用于把资料与查询转换成可检索的向量。"))
        self.active = label("")
        layout.addWidget(self.active)
        self.override_note = label("")
        self.override_note.setProperty("muted", True)
        layout.addWidget(self.override_note)
        self.fields = {}
        self.provider = QComboBox()
        self.provider.addItem("本地 Ollama" if section == "chat" else "本地 Sentence Transformers", "local")
        self.provider.addItem("云端 / OpenAI 兼容", "cloud")
        self.fields["provider"] = self.provider
        form = QFormLayout()
        form.addRow("服务类型", self.provider)
        layout.addLayout(form)
        self.local_panel, self.cloud_panel = QWidget(), QWidget()
        local, cloud = QFormLayout(self.local_panel), QFormLayout(self.cloud_panel)
        local.setContentsMargins(0, 0, 0, 0)
        cloud.setContentsMargins(0, 0, 0, 0)
        self.local_model = QComboBox()
        self.local_model.setEditable(True)
        self.fields["local_model"] = self.local_model
        local.addRow("模型名称 / 路径", self.local_model)
        if section == "chat":
            self._text(local, "local_base_url", "服务地址")
            self._number(local, "local_timeout_seconds", "超时（秒）")
        else:
            local.addRow(label("可填写 Hugging Face 模型名或本地模型目录。首次测试可能下载模型。"))
        self._text(cloud, "cloud_model", "模型名称")
        self._text(cloud, "cloud_base_url", "服务地址（含 /v1）")
        self._number(cloud, "cloud_timeout_seconds", "超时（秒）")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("留空沿用已保存密钥；更换服务时重新填写")
        self.fields["cloud_api_key"] = self.key
        cloud.addRow("API Key", self.key)
        self.clear_key = QPushButton("清除已保存密钥")
        cloud.addRow("", self.clear_key)
        cloud.addRow(label("密钥保存在系统凭据库，页面不回显。云端连接测试会发送固定短文本，可能计费。"))
        layout.addWidget(self.local_panel)
        layout.addWidget(self.cloud_panel)
        if section == "embedding":
            batch_form = QFormLayout()
            batch = QSpinBox()
            batch.setRange(1, max(4096, settings.batch_size))
            self.fields["batch_size"] = batch
            batch_form.addRow("批大小", batch)
            layout.addLayout(batch_form)
        self.note = label("")
        layout.addWidget(self.note)
        actions = QHBoxLayout()
        self.refresh_models = QPushButton("刷新 Ollama 模型")
        self.test = QPushButton("测试连接")
        self.apply = QPushButton("保存并应用" if section == "chat" else "重建并切换")
        self.apply.setProperty("primary", True)
        if section == "chat":
            actions.addWidget(self.refresh_models)
        actions.addStretch()
        actions.addWidget(self.test)
        actions.addWidget(self.apply)
        layout.addLayout(actions)
        self.reset(settings, sources)
        for name, widget in self.fields.items():
            widget.setObjectName(f"{section}_{name}")
            widget.setAccessibleName(f"{title.text()} {name}")
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._changed)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._changed)
            else:
                widget.valueChanged.connect(self._changed)

    def _text(self, layout, name, caption):
        self.fields[name] = QLineEdit()
        layout.addRow(caption, self.fields[name])

    def _number(self, layout, name, caption):
        widget = QDoubleSpinBox()
        widget.setRange(0.1, max(86400, getattr(self.base, name)))
        widget.setDecimals(1)
        self.fields[name] = widget
        layout.addRow(caption, widget)

    def reset(self, settings, sources):
        self.base, self.sources = settings, sources
        for name, widget in self.fields.items():
            widget.blockSignals(True)
            if name == "cloud_api_key":
                widget.clear()
            elif name == "provider":
                widget.setCurrentIndex(widget.findData(settings.provider))
            elif name == "local_model":
                widget.setCurrentText(settings.local_model)
            elif isinstance(widget, QLineEdit):
                widget.setText(getattr(settings, name))
            else:
                widget.setValue(getattr(settings, name))
            widget.blockSignals(False)
        self.update_controls()

    def update_controls(self):
        local = self.provider.currentData() == "local"
        self.local_panel.setVisible(local)
        self.cloud_panel.setVisible(not local)
        self.refresh_models.setEnabled(local and "local_model" not in self.sources)
        for name, widget in self.fields.items():
            widget.setEnabled(name not in self.sources)
            widget.setToolTip(self.sources.get(name, ""))
        self.clear_key.setEnabled("cloud_api_key" not in self.sources)
        self.override_note.setText("外部配置优先，相应字段已锁定：\n" + "\n".join(self.sources.values()) if self.sources else "")
        self.override_note.setVisible(bool(self.sources))

    def _changed(self, *_):
        self.update_controls()
        self.changed.emit()

    def draft(self):
        values = self.base.model_dump(exclude={"cloud_api_key"})
        for name, widget in self.fields.items():
            if name == "cloud_api_key":
                continue
            if name == "provider":
                values[name] = widget.currentData()
            elif name == "local_model":
                values[name] = widget.currentText().strip()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text().strip()
            else:
                values[name] = widget.value()
        return type(self.base).model_validate(values)


class ModelSettingsPage(PageShell):
    progress_received = Signal(object)

    def __init__(self, runtime, service=None):
        super().__init__("模型设置", "配置本地或云端模型，并在切换前验证连接。")
        self.runtime = runtime
        self.service = service or ModelSettingsService(runtime.config_path)
        self._task = None
        self._action = None
        self._cancel = Event()
        self.active_embedding = runtime.active_embedding_settings()
        settings = load_settings(self.service.config_path, self.service.env_file)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self.chat = ModelForm("chat", settings.chat, self.service.field_sources("chat"))
        self.embedding = ModelForm("embedding", settings.embedding, self.service.field_sources("embedding"))
        for form in (self.chat, self.embedding):
            layout.addWidget(form)
            form.test.clicked.connect(lambda _=False, f=form: self.test_connection(f))
            form.clear_key.clicked.connect(lambda _=False, f=form: self.clear_credential(f))
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.set_content(scroll)
        self.refresh = QPushButton("重新加载")
        self.actions.addWidget(self.refresh)
        self.feedback = label("设置仅在保存或重建成功后生效。")
        self.layout().addWidget(self.feedback)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.layout().addWidget(self.progress)
        self.cancel = QPushButton("取消重建")
        self.cancel.setVisible(False)
        self.layout().addWidget(self.cancel)
        self.cancel.clicked.connect(self.cancel_rebuild)
        self.refresh.clicked.connect(self.reload)
        self.chat.refresh_models.clicked.connect(self.ollama_models)
        self.chat.apply.clicked.connect(self.save_chat)
        self.embedding.apply.clicked.connect(self.rebuild)
        self.embedding.changed.connect(self.update_summary)
        self.progress_received.connect(self.show_progress)
        self.update_summary()

    @property
    def busy(self):
        return self._task is not None

    def update_summary(self):
        self.chat.active.setText("当前生效：" + model_caption(self.runtime.settings.chat))
        self.embedding.active.setText("当前生效：" + model_caption(self.active_embedding))
        candidate = self.embedding.draft()
        changed = embedding_profile_fingerprint(candidate) != embedding_profile_fingerprint(self.active_embedding)
        count = len(self.runtime.collections.list_all())
        self.embedding.note.setText(
            f"待应用：{model_caption(candidate)}。需要重建 {count} 个集合；完成前继续使用旧索引。"
            if changed else "配置与当前生效模型一致。"
        )
        self.embedding.apply.setEnabled(changed)

    def snapshot(self, form):
        try:
            draft = form.draft()
            self.service.validate_candidate(draft, require_key=False)
            return draft, form.key.text().strip() or None
        except ValueError:
            self.feedback.setText("请检查模型名称、HTTP(S) 服务地址和数值字段；服务地址不能包含密码或查询参数。")
            return None

    def confirm(self, title, text):
        return QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def _run(self, action, function, success, failure):
        if self.busy:
            return False
        self._action, self._success = action, success
        self._cancel.clear()
        for widget in (self.chat, self.embedding, self.refresh):
            widget.setEnabled(False)
        self.feedback.setText("正在重建：导入和删除操作暂时暂停。" if action == "rebuild" else "处理中…")
        self.progress.setVisible(action == "rebuild")
        self.progress.setRange(0, 0)
        self.cancel.setVisible(action == "rebuild")
        self.cancel.setEnabled(True)

        def safe_call():
            try:
                return function()
            except EmbeddingRebuildCancelled:
                raise RuntimeError("重建已取消，旧索引继续生效。") from None
            except Exception:
                # Provider exceptions can contain response bodies, URLs or API keys.
                raise RuntimeError(failure) from None

        task = BackgroundTask(action, safe_call)
        self._task = task
        task.signals.succeeded.connect(self._succeeded)
        task.signals.failed.connect(self._failed)
        task.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(task)
        return True

    @Slot(object, object)
    def _succeeded(self, _token, result):
        self._success(result)

    @Slot(object, str)
    def _failed(self, _token, message):
        self.feedback.setText(message)
        self.progress.setVisible(False)

    @Slot(object)
    def _finished(self, _token):
        self._task = None
        self._action = None
        self._success = None
        for widget in (self.chat, self.embedding, self.refresh):
            widget.setEnabled(True)
        for form in (self.chat, self.embedding):
            form.key.clear()
            form.update_controls()
        self.cancel.setVisible(False)
        self.update_summary()

    def test_connection(self, form):
        if self.busy:
            return
        snapshot = self.snapshot(form)
        if snapshot is None:
            return
        draft, key = snapshot
        if draft.provider == "cloud" and not self.confirm("测试云端连接", "将向配置的服务发送固定短文本，不发送知识库资料；服务可能计费。是否继续？"):
            return
        def test():
            candidate = self.service.prepare(form.section, draft, key)
            self._check_confirmed_target(draft, candidate)
            (self.service.test_chat if form.section == "chat" else self.service.test_embedding)(candidate)
        self._run("test", test, lambda _: self.feedback.setText("连接测试成功，尚未更改生效配置。"),
                  "连接测试失败。请检查服务是否启动、地址、模型名称及 API Key；本地模型首次加载可能需要网络。")

    def ollama_models(self):
        snapshot = self.snapshot(self.chat)
        if snapshot is None:
            return
        draft, _ = snapshot
        self._run("models", lambda: self.service.ollama_models(draft.local_base_url, draft.local_timeout_seconds),
                  self._show_models, "无法读取 Ollama 模型列表。请检查服务地址，并确认 Ollama 已启动。")

    def _show_models(self, names):
        selected = self.chat.local_model.currentText()
        self.chat.local_model.clear()
        self.chat.local_model.addItems(names)
        self.chat.local_model.setCurrentText(selected)
        self.feedback.setText(f"发现 {len(names)} 个已安装模型；也可手动输入模型名称。")

    def save_chat(self):
        snapshot = self.snapshot(self.chat)
        if snapshot is None:
            return
        draft, key = snapshot
        def save():
            candidate = self.service.prepare("chat", draft, key)
            loaded = self.service.save_chat(candidate, key)
            self.runtime.settings.chat = loaded.chat
            return loaded.chat
        def saved(settings):
            self.chat.reset(settings, self.service.field_sources("chat"))
            self.feedback.setText("问答与生成配置已保存，下次请求立即使用新模型。")
        self._run("save", save, saved, "保存失败。请检查配置文件权限、系统凭据库和 API Key 后重试。")

    def rebuild(self):
        if self.busy:
            return
        snapshot = self.snapshot(self.embedding)
        if snapshot is None:
            return
        draft, key = snapshot
        count = len(self.runtime.collections.list_all())
        if not self.confirm("重建并切换嵌入模型", f"将重建 {count} 个集合，期间暂停导入和删除。完成后切换；失败或取消时继续使用旧索引。\n"
                            + ("所有当前资料切片将发送给配置的云端嵌入服务，可能计费。" if draft.provider == "cloud" else "本地模型首次加载可能需要下载。") + "\n是否继续？"):
            return
        def rebuild():
            candidate = self.service.prepare("embedding", draft, key)
            self._check_confirmed_target(draft, candidate)
            return self.runtime.rebuild_embeddings(candidate, on_progress=self.progress_received.emit,
                                                   should_cancel=self._cancel.is_set)
        def completed(result):
            self.active_embedding = self.runtime.active_embedding_settings()
            self.embedding.reset(self.active_embedding, self.service.field_sources("embedding"))
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.feedback.setText(result.configuration_warning or f"已切换嵌入模型，完成 {result.chunk_count} 个切片。")
        self._run("rebuild", rebuild, completed, "重建未完成。请检查模型服务和存储权限，重新加载当前状态后重试。")

    @Slot(object)
    def show_progress(self, progress):
        self.progress.setRange(0, max(1, progress.total_chunks))
        self.progress.setValue(progress.completed_chunks)
        self.progress.setFormat(f"{progress.completed_chunks} / {progress.total_chunks} 个切片")
        if progress.source_id is not None:
            self.feedback.setText(f"正在重建集合 {progress.collection_id} / 资料 {progress.source_id}；导入和删除暂时暂停。")

    @staticmethod
    def _check_confirmed_target(draft, candidate):
        # External overrides may change while the confirmation dialog is open.
        fields = ("provider", "cloud_base_url", "cloud_model", "local_model")
        if any(getattr(draft, field) != getattr(candidate, field) for field in fields):
            raise ValueError("配置来源已变化，请重新加载并确认目标服务。")

    def cancel_rebuild(self):
        self._cancel.set()
        self.cancel.setEnabled(False)
        self.feedback.setText("已请求取消，等待当前模型请求结束并清理暂存向量…")

    def clear_credential(self, form):
        if self.busy or not self.confirm("清除已保存密钥", "清除后该云端模型将无法使用，直到重新填写密钥。是否继续？"):
            return
        draft = form.draft()
        def clear():
            self.service.clear_credential(form.section, draft)
            current = getattr(self.runtime.settings, form.section)
            same_target = (chat_credential_name(current) == chat_credential_name(draft) if form.section == "chat"
                           else embedding_profile_fingerprint(current) == embedding_profile_fingerprint(draft))
            if same_target:
                setattr(self.runtime.settings, form.section, current.model_copy(update={"cloud_api_key": None}))
        self._run("clear", clear, lambda _: self.feedback.setText("已清除系统凭据库中的密钥。"), "清除失败，请检查系统凭据库或外部配置来源。")

    def reload(self):
        def load():
            return self.service.load(), self.runtime.active_embedding_settings()
        def loaded(result):
            settings, self.active_embedding = result
            self.runtime.settings.chat = settings.chat
            self.chat.reset(settings.chat, self.service.field_sources("chat"))
            self.embedding.reset(settings.embedding, self.service.field_sources("embedding"))
            self.feedback.setText("已重新加载配置和当前生效状态。")
        self._run("reload", load, loaded, "加载失败，请检查配置文件格式及系统凭据库。")
