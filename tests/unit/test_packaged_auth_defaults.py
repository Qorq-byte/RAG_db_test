"""The Windows launcher must keep new and existing installations sign-in ready."""

import importlib.util
import os
from pathlib import Path

from ragdb.config import load_settings


LAUNCHER = Path(__file__).resolve().parents[2] / "packaging" / "launcher.py"
spec = importlib.util.spec_from_file_location("ragdb_frozen_launcher", LAUNCHER)
assert spec is not None and spec.loader is not None
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_blank_existing_auth_uses_bundled_public_client(tmp_path, monkeypatch):
    monkeypatch.delenv("RAGDB_AUTH__URL", raising=False)
    monkeypatch.delenv("RAGDB_AUTH__PUBLISHABLE_KEY", raising=False)
    config = tmp_path / "config.toml"
    original = '[auth]\nurl = ""\npublishable_key = ""\n'
    config.write_text(original, encoding="utf-8")

    launcher.apply_public_auth_defaults(config)
    settings = load_settings(config, tmp_path / ".env")

    assert settings.auth.url == launcher.PUBLIC_AUTH_URL
    assert settings.auth.publishable_key == launcher.PUBLIC_AUTH_KEY
    assert config.read_text(encoding="utf-8") == original


def test_custom_auth_is_never_replaced(tmp_path, monkeypatch):
    monkeypatch.delenv("RAGDB_AUTH__URL", raising=False)
    monkeypatch.delenv("RAGDB_AUTH__PUBLISHABLE_KEY", raising=False)
    config = tmp_path / "config.toml"
    config.write_text('[auth]\nurl = "https://custom.example"\npublishable_key = "other"\n',
                      encoding="utf-8")

    launcher.apply_public_auth_defaults(config)
    settings = load_settings(config, tmp_path / ".env")

    assert settings.auth.url == "https://custom.example"
    assert settings.auth.publishable_key == "other"
    assert "RAGDB_AUTH__URL" not in os.environ


def test_explicit_environment_auth_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("RAGDB_AUTH__URL", "https://override.example")
    monkeypatch.setenv("RAGDB_AUTH__PUBLISHABLE_KEY", "override")
    config = tmp_path / "config.toml"
    config.write_text('[auth]\nurl = ""\npublishable_key = ""\n', encoding="utf-8")

    launcher.apply_public_auth_defaults(config)
    settings = load_settings(config, tmp_path / ".env")

    assert settings.auth.url == "https://override.example"
    assert settings.auth.publishable_key == "override"
