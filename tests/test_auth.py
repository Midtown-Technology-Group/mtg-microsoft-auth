from pathlib import Path

import pytest

from mtg_microsoft_auth.models import AuthConfig, AuthMode
from mtg_microsoft_auth.session import GraphAuthSession
from mtg_microsoft_auth import cli


class StubApp:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.interactive_kwargs: dict | None = None

    def get_accounts(self):
        return [{"username": "user@example.com"}]

    def acquire_token_silent_with_error(self, scopes, account, force_refresh=False):
        self.calls.append("wam")
        return None

    def acquire_token_interactive(self, scopes, **kwargs):
        self.calls.append("interactive")
        self.interactive_kwargs = kwargs
        return {"access_token": "interactive-token"}

    def acquire_token_silent(self, scopes, account):
        self.calls.append("silent")
        return None

    def initiate_device_flow(self, scopes):
        self.calls.append("device-init")
        return {"user_code": "ABC", "message": "Sign in"}

    def acquire_token_by_device_flow(self, flow):
        self.calls.append("device")
        return {"access_token": "device-token"}


def build_config(**overrides):
    base = AuthConfig(
        client_id="11111111-1111-1111-1111-111111111111",
        tenant_id="22222222-2222-2222-2222-222222222222",
        scopes=["Tasks.Read", "Tasks.ReadWrite"],
        cache_namespace="todo-cli",
    )
    return base.model_copy(update=overrides)


def test_prefers_wam_then_interactive(monkeypatch):
    app = StubApp()
    session = GraphAuthSession(build_config(mode=AuthMode.AUTO), app_factory=lambda *_: app)
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)

    token = session.acquire_token()

    assert token == "interactive-token"
    assert app.calls == ["wam", "interactive"]


def test_uses_device_code_when_interactive_unavailable(monkeypatch):
    app = StubApp()
    session = GraphAuthSession(build_config(mode=AuthMode.AUTO), app_factory=lambda *_: app)
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)
    monkeypatch.setattr(session, "_try_wam_token", lambda: None)
    monkeypatch.setattr(session, "_try_interactive_token", lambda: None)

    token = session.acquire_token()

    assert token == "device-token"
    assert app.calls == ["device-init", "device"]


def test_raises_clear_error_when_all_flows_fail(monkeypatch):
    session = GraphAuthSession(build_config(mode=AuthMode.AUTO), app_factory=lambda *_: StubApp())
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)
    monkeypatch.setattr(session, "_try_wam_token", lambda: None)
    monkeypatch.setattr(session, "_try_interactive_token", lambda: None)
    monkeypatch.setattr(session, "_try_device_code_token", lambda: None)

    with pytest.raises(RuntimeError, match="Unable to acquire Microsoft Graph access token"):
        session.acquire_token()


def test_windows_cache_path_uses_namespace(monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(Path("C:/Users/TestUser")))
    config = build_config(cache_namespace="midtown-auth")

    path = config.cache_path()

    assert path.name == "token_cache.bin"
    assert "midtown-auth" in str(path)


def test_wam_mode_does_not_fall_back_to_browser_or_device(monkeypatch):
    session = GraphAuthSession(build_config(mode=AuthMode.WAM), app_factory=lambda *_: StubApp())
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)
    monkeypatch.setattr(session, "_try_wam_token", lambda: None)

    with pytest.raises(RuntimeError, match="Unable to acquire Microsoft Graph access token"):
        session.acquire_token()


def test_account_hint_prioritizes_matching_cached_account():
    class HintApp(StubApp):
        def get_accounts(self):
            return [
                {"username": "other@example.com"},
                {"username": "user@example.com"},
            ]

        def acquire_token_silent_with_error(self, scopes, account, force_refresh=False):
            self.calls.append(f"wam:{account['username']}")
            if account["username"] == "user@example.com":
                return {"access_token": "hinted-token"}
            return None

    app = HintApp()
    session = GraphAuthSession(
        build_config(mode=AuthMode.WAM, account_hint="user@example.com"),
        app_factory=lambda *_: app,
    )

    token = session.acquire_token()

    assert token == "hinted-token"
    assert app.calls == ["wam:user@example.com"]


def test_cli_default_scopes_cover_read_only_toys():
    assert cli.DEFAULT_SCOPES == [
        "User.Read",
        "Calendars.Read",
        "Mail.Read",
        "Mail.ReadBasic",
        "Chat.Read",
        "Files.Read",
        "Tasks.Read",
    ]


def test_cli_login_wires_shared_config(monkeypatch, capsys):
    captured = {}

    class StubSession:
        def __init__(self, config):
            captured["config"] = config

    class StubClient:
        def __init__(self, session):
            captured["session"] = session

        def get(self, path, params=None):
            captured["path"] = path
            captured["params"] = params
            return {"userPrincipalName": "user@example.com"}

    monkeypatch.setattr(cli, "GraphAuthSession", StubSession)
    monkeypatch.setattr(cli, "GraphClient", StubClient)

    result = cli.main(["login", "--account", "user@example.com"])

    assert result == 0
    assert captured["config"].client_id == cli.DEFAULT_CLIENT_ID
    assert captured["config"].tenant_id == cli.DEFAULT_TENANT_ID
    assert captured["config"].cache_namespace == cli.DEFAULT_CACHE_NAMESPACE
    assert captured["config"].account_hint == "user@example.com"
    assert captured["config"].mode == AuthMode.AUTO
    assert captured["config"].scopes == cli.DEFAULT_SCOPES
    assert captured["path"] == "/me"
    assert captured["params"] == {"$select": "displayName,userPrincipalName"}
    assert "Authenticated user@example.com" in capsys.readouterr().out


def test_interactive_mode_passes_console_handle_when_broker_enabled(monkeypatch):
    app = StubApp()
    session = GraphAuthSession(
        build_config(mode=AuthMode.INTERACTIVE, allow_broker=True),
        app_factory=lambda *_: app,
    )
    monkeypatch.setattr(
        "mtg_microsoft_auth.session._get_console_window_handle", lambda: 123
    )

    token = session.acquire_token()

    assert token == "interactive-token"
    assert app.interactive_kwargs["parent_window_handle"] == 123
