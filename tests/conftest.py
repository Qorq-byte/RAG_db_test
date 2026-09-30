"""Keep legacy command tests focused on their storage behavior.

Authentication is exercised separately in test_auth_cli.py; existing CLI cases
use a verified test identity and their original temporary data directories.
"""

from uuid import UUID

import pytest


@pytest.fixture(autouse=True)
def authenticated_legacy_cli(monkeypatch, request):
    if request.node.get_closest_marker("real_auth"):
        return
    import ragdb.cli as cli
    from ragdb.auth import AuthSession

    class VerifiedTestAuth:
        def __init__(self, _settings):
            pass

        def restore(self):
            return AuthSession(
                UUID("adad7c76-3f69-4c47-a9bb-1b03fef6653c"),
                "verified@example.test", "access", "refresh", 2**31,
            )

        def close(self):
            pass

    monkeypatch.setattr(cli, "AuthService", VerifiedTestAuth)
    monkeypatch.setattr(cli, "account_settings", lambda settings, _user_id: settings)
