"""CLI must reject every knowledgebase command until online email verification."""

from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

import ragdb.cli as cli
from ragdb.auth import AuthError, AuthSession
from ragdb.config import AppSettings, AuthSettings, StorageSettings


pytestmark = pytest.mark.real_auth
runner = CliRunner()


def test_unconfigured_cli_cannot_open_library():
    result = runner.invoke(cli.app, ["collection", "list"])
    assert result.exit_code == cli.ExitCode.USAGE_ERROR
    assert "登录要求" in result.output
    assert runner.invoke(cli.app, ["version"]).exit_code == 0


def test_failed_session_blocks_backup_and_index(monkeypatch):
    class OfflineAuth:
        def __init__(self, _settings):
            pass

        def restore(self):
            raise AuthError("认证服务暂时无法连接")

        def close(self):
            pass

    monkeypatch.setattr(cli, "load_settings", lambda **_: AppSettings(auth=AuthSettings(
        url="https://example.supabase.co", publishable_key="sb_publishable_test"
    )))
    monkeypatch.setattr(cli, "AuthService", OfflineAuth)
    for args in (["collection", "list"], ["index", "list-stale"], ["backup", "verify", "anything.zip"]):
        result = runner.invoke(cli.app, args)
        assert result.exit_code == cli.ExitCode.USAGE_ERROR
        assert "认证服务暂时无法连接" in result.output


def test_verified_account_scopes_cli_settings(monkeypatch):
    user_id = UUID("adad7c76-3f69-4c47-a9bb-1b03fef6653c")
    settings = AppSettings(
        auth=AuthSettings(url="https://example.supabase.co", publishable_key="sb_publishable_test"),
        storage=StorageSettings(data_dir=Path("private-library")),
    )

    class VerifiedAuth:
        def __init__(self, _settings):
            pass

        def restore(self):
            return AuthSession(user_id, "a@example.com", "access", "refresh", 2**31)

        def close(self):
            pass

    observed = []
    monkeypatch.setattr(cli, "load_settings", lambda **_: settings)
    monkeypatch.setattr(cli, "AuthService", VerifiedAuth)
    monkeypatch.setattr(cli, "_collection_service", lambda ctx: observed.append(ctx.find_root().obj["settings"].storage.data_dir) or type("CollectionService", (), {"list_all": lambda self: []})())
    result = runner.invoke(cli.app, ["collection", "list"])
    assert result.exit_code == 0, result.output
    assert observed == [Path("private-library") / "accounts" / str(user_id)]
