import os
import time
from threading import Event
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QLineEdit

from ragdb.application.model_settings import ModelSettingsService
from ragdb.application.embedding_rebuild import EmbeddingRebuildCancelled, EmbeddingRebuildProgress
from ragdb.config import AppSettings, StorageSettings, EmbeddingSettings, load_settings
from ragdb.desktop.model_settings_page import ModelSettingsPage
from ragdb.desktop.window import MainWindow, PAGES
from ragdb.infrastructure.database import SQLiteDatabase
from ragdb.runtime import ApplicationRuntime


APPLICATION = QApplication.instance() or QApplication([])


class Credentials:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


@pytest.fixture
def page(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text(f"[storage]\ndata_dir = '{tmp_path.as_posix()}'\n", encoding="utf-8")
    database = SQLiteDatabase(tmp_path / "ragdb.sqlite3")
    database.initialize()
    credentials = Credentials()
    monkeypatch.setattr("ragdb.runtime.SystemCredentialStore", lambda: credentials)
    monkeypatch.setattr("ragdb.application.model_settings.SystemCredentialStore", lambda: credentials)
    runtime = ApplicationRuntime(AppSettings(storage=StorageSettings(data_dir=tmp_path)), database, config)
    service = ModelSettingsService(config, tmp_path / ".env", credentials)
    widget = ModelSettingsPage(runtime, service)
    widget.show()
    yield widget
    widget._cancel.set()
    if widget.busy:
        finish(widget)
    widget.close()
    APPLICATION.processEvents()


def finish(page):
    deadline = time.monotonic() + 10
    while page.busy and time.monotonic() < deadline:
        APPLICATION.processEvents()
        time.sleep(0.005)
    APPLICATION.processEvents()
    assert not page.busy, "model settings task did not finish"


def test_navigation_opens_real_settings_page(page):
    window = MainWindow(page.runtime)
    window.navigation.select_page(PAGES.index("模型设置"))
    assert window.pages.currentWidget() is window.model_settings_page
    window.close()


def test_form_provider_visibility_password_and_rebuild_difference(page):
    assert page.chat.local_panel.isVisible()
    page.chat.provider.setCurrentIndex(1)
    assert page.chat.cloud_panel.isVisible()
    assert page.chat.local_panel.isHidden()
    assert page.chat.key.echoMode() == QLineEdit.EchoMode.Password
    assert page.chat.key.text() == ""
    assert not page.embedding.apply.isEnabled()
    page.embedding.local_model.setCurrentText("replacement")
    assert page.embedding.apply.isEnabled()
    assert "需要重建 0 个集合" in page.embedding.note.text()
    assert page.runtime.settings.embedding.local_model != "replacement"


def test_chat_save_is_immediate_and_restores_after_restart(page):
    page.chat.local_model.setCurrentText("local-chat-new")
    page.save_chat()
    finish(page)
    assert page.runtime.settings.chat.local_model == "local-chat-new"
    assert ApplicationRuntime.from_config(page.service.config_path).settings.chat.local_model == "local-chat-new"
    assert "已保存" in page.feedback.text()


def test_cloud_key_stays_in_vault_and_is_not_repopulated(page):
    page.chat.provider.setCurrentIndex(1)
    page.chat.fields["cloud_model"].setText("cloud-chat")
    page.chat.key.setText("private-test-key")
    page.save_chat()
    finish(page)
    assert page.runtime.settings.chat.cloud_api_key.get_secret_value() == "private-test-key"
    assert "private-test-key" not in page.service.config_path.read_text(encoding="utf-8")
    assert page.chat.key.text() == ""
    restarted = ApplicationRuntime.from_config(page.service.config_path)
    assert restarted.settings.chat.cloud_api_key.get_secret_value() == "private-test-key"
    page.reload()
    finish(page)
    assert page.chat.key.text() == ""


def test_environment_fields_and_dotenv_sources_are_locked(page, monkeypatch):
    page.service.env_file.write_text("RAGDB_CHAT__LOCAL_MODEL=dotenv-chat\n", encoding="utf-8")
    monkeypatch.setenv("RAGDB_CHAT__LOCAL_MODEL", "env-chat")
    monkeypatch.setenv("RAGDB_CHAT", '{"local_timeout_seconds": 17}')
    page.reload()
    finish(page)
    assert page.chat.local_model.currentText() == "env-chat"
    assert not page.chat.local_model.isEnabled()
    assert not page.chat.fields["local_timeout_seconds"].isEnabled()
    assert "环境变量" in page.chat.override_note.text()
    monkeypatch.delenv("RAGDB_CHAT__LOCAL_MODEL")
    page.reload()
    finish(page)
    assert page.chat.local_model.currentText() == "dotenv-chat"
    assert ".env" in page.chat.override_note.text()


def test_connection_runs_in_worker_and_suppresses_secret_errors(page, monkeypatch):
    called = []
    def fail(settings):
        called.append(QThread.currentThread() != APPLICATION.thread())
        raise RuntimeError("provider response private-test-key")
    page.chat.provider.setCurrentIndex(1)
    page.chat.key.setText("private-test-key")
    monkeypatch.setattr(page, "confirm", lambda *args: True)
    monkeypatch.setattr(page.service, "test_chat", fail)
    before = page.service.config_path.read_bytes()
    page.test_connection(page.chat)
    finish(page)
    assert called == [True]
    assert "失败" in page.feedback.text()
    assert "private-test-key" not in page.feedback.text()
    assert page.service.config_path.read_bytes() == before


def test_declining_cloud_confirmation_does_not_send_request(page, monkeypatch):
    page.chat.provider.setCurrentIndex(1)
    page.chat.key.setText("private-test-key")
    monkeypatch.setattr(page, "confirm", lambda *args: False)
    monkeypatch.setattr(page.service, "test_chat", lambda _: pytest.fail("unexpected request"))
    page.test_connection(page.chat)
    assert not page.busy


def test_ollama_list_retains_manual_selection(page, monkeypatch):
    page.chat.local_model.setCurrentText("manual-model")
    monkeypatch.setattr(page.service, "ollama_models", lambda *args: ["installed-a", "installed-b"])
    page.ollama_models()
    finish(page)
    assert page.chat.local_model.currentText() == "manual-model"
    assert page.chat.local_model.findText("installed-a") >= 0


def test_ollama_embedding_form_refresh_and_candidate(page, monkeypatch):
    form = page.embedding
    form.provider.setCurrentIndex(form.provider.findData("ollama"))
    assert form.ollama_panel.isVisible()
    assert form.local_panel.isHidden() and form.cloud_panel.isHidden()
    assert form.refresh_models.isVisible()
    form.ollama_model.setCurrentText("embeddinggemma:latest")
    assert form.draft().provider == "ollama"
    assert form.draft().ollama_model == "embeddinggemma:latest"
    monkeypatch.setattr(page.service, "ollama_models", lambda *args: ["embeddinggemma:latest"])
    page.ollama_models(form)
    finish(page)
    assert form.ollama_model.currentText() == "embeddinggemma:latest"


def test_busy_task_blocks_duplicates_and_cancellation_preserves_active_model(page, monkeypatch):
    started, release = Event(), Event()
    def rebuild(settings, on_progress, should_cancel):
        started.set()
        on_progress(EmbeddingRebuildProgress(1, 2))
        assert release.wait(5)
        if should_cancel():
            raise EmbeddingRebuildCancelled()
        raise AssertionError("expected cancellation")
    monkeypatch.setattr(page.runtime, "rebuild_embeddings", rebuild)
    monkeypatch.setattr(page, "confirm", lambda *args: True)
    page.embedding.local_model.setCurrentText("replacement")
    page.rebuild()
    try:
        assert started.wait(5)
        deadline = time.monotonic() + 5
        while page.progress.value() != 1 and time.monotonic() < deadline:
            APPLICATION.processEvents()
            time.sleep(0.005)
        assert not page.chat.isEnabled() and not page.refresh.isEnabled()
        assert page.progress.value() == 1
        assert not page._run("duplicate", lambda: None, lambda _: None, "error")
        page.cancel_rebuild()
    finally:
        release.set()
    finish(page)
    assert "已取消" in page.feedback.text()
    assert page.runtime.settings.embedding.local_model != "replacement"
    assert page.embedding.apply.isEnabled()


def test_real_empty_rebuild_updates_active_model_and_persisted_config(page, monkeypatch):
    monkeypatch.setattr(page, "confirm", lambda *args: True)
    provider = SimpleNamespace(embed_texts=lambda texts: [[0.1, 0.2] for _ in texts])
    monkeypatch.setattr("ragdb.application.embedding_rebuild.create_embedding_provider", lambda _: provider)
    page.embedding.local_model.setCurrentText("replacement")
    page.rebuild()
    finish(page)
    assert page.active_embedding.local_model == "replacement"
    assert "已切换" in page.feedback.text()
    assert load_settings(page.service.config_path).embedding.local_model == "replacement"
    assert not page.embedding.apply.isEnabled()


def test_failed_rebuild_can_retry_without_applying_candidate(page, monkeypatch):
    monkeypatch.setattr(page, "confirm", lambda *args: True)
    def fail(*args, **kwargs):
        raise RuntimeError("disk failure")
    monkeypatch.setattr(page.runtime, "rebuild_embeddings", fail)
    page.embedding.local_model.setCurrentText("replacement")
    page.rebuild()
    finish(page)
    assert "未完成" in page.feedback.text()
    assert page.active_embedding.local_model != "replacement"
    assert page.embedding.apply.isEnabled()
    assert page.embedding.local_model.currentText() == "replacement"
    assert page.progress.isHidden()


def test_clear_key_respects_vault_and_external_management(page, monkeypatch):
    page.chat.provider.setCurrentIndex(1)
    page.chat.key.setText("private-test-key")
    page.save_chat()
    finish(page)
    monkeypatch.setattr(page, "confirm", lambda *args: True)
    page.clear_credential(page.chat)
    finish(page)
    assert not page.service.credentials.values
    assert page.runtime.settings.chat.cloud_api_key is None
    monkeypatch.setenv("RAGDB_CHAT__CLOUD_API_KEY", "external-key")
    page.reload()
    finish(page)
    assert not page.chat.clear_key.isEnabled()
    assert not page.chat.key.isEnabled()
    assert page.chat.key.text() == ""


def test_external_target_change_after_confirmation_does_not_send(page, monkeypatch):
    monkeypatch.setenv("RAGDB_CHAT__PROVIDER", "cloud")
    monkeypatch.setenv("RAGDB_CHAT__CLOUD_API_KEY", "external-key")
    monkeypatch.setattr(page.service, "test_chat", lambda _: pytest.fail("unconfirmed cloud request"))
    page.test_connection(page.chat)
    finish(page)
    assert "失败" in page.feedback.text()


def test_close_during_rebuild_waits_and_requests_cancel(page):
    window = MainWindow(page.runtime)
    window.show()
    widget = window.model_settings_page
    started, release = Event(), Event()
    def work():
        started.set()
        assert release.wait(5)
    widget._run("rebuild", work, lambda _: None, "failed")
    try:
        assert started.wait(5)
        assert not window.close()
        assert window.isVisible()
        assert widget._cancel.is_set()
    finally:
        release.set()
        finish(widget)
        window.close()
