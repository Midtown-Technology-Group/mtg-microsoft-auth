import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mtg_microsoft_auth import cli
from mtg_microsoft_auth.models import AuthConfig, AuthMode
from mtg_microsoft_auth.session import GraphAuthSession


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


def synthetic_token(**overrides):
    claims = {
        "aud": "https://graph.microsoft.com",
        "azp": "11111111-1111-1111-1111-111111111111",
        "tid": "22222222-2222-2222-2222-222222222222",
        "scp": "Tasks.Read Tasks.ReadWrite",
        "preferred_username": "user@example.com",
    }
    claims.update(overrides)
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"synthetic.{payload}.signature"


def test_prefers_wam_then_interactive(monkeypatch):
    app = StubApp()
    session = GraphAuthSession(
        build_config(mode=AuthMode.AUTO), app_factory=lambda *_: app
    )
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)

    token = session.acquire_token()

    assert token == "interactive-token"
    assert app.calls == ["wam", "interactive"]


def test_uses_device_code_when_interactive_unavailable(monkeypatch):
    app = StubApp()
    session = GraphAuthSession(
        build_config(mode=AuthMode.AUTO), app_factory=lambda *_: app
    )
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)
    monkeypatch.setattr(session, "_try_wam_token", lambda: None)
    monkeypatch.setattr(session, "_try_interactive_token", lambda: None)

    token = session.acquire_token()

    assert token == "device-token"
    assert app.calls == ["device-init", "device"]


def test_raises_clear_error_when_all_flows_fail(monkeypatch):
    session = GraphAuthSession(
        build_config(mode=AuthMode.AUTO), app_factory=lambda *_: StubApp()
    )
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)
    monkeypatch.setattr(session, "_try_wam_token", lambda: None)
    monkeypatch.setattr(session, "_try_interactive_token", lambda: None)
    monkeypatch.setattr(session, "_try_device_code_token", lambda: None)

    with pytest.raises(
        RuntimeError, match="Unable to acquire Microsoft Graph access token"
    ):
        session.acquire_token()


def test_windows_cache_path_uses_namespace(monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(Path("C:/Users/TestUser")))
    config = build_config(cache_namespace="midtown-auth")

    path = config.cache_path()

    assert path.name == "token_cache.bin"
    assert "midtown-auth" in str(path)


def test_wam_mode_does_not_fall_back_to_browser_or_device(monkeypatch):
    session = GraphAuthSession(
        build_config(mode=AuthMode.WAM), app_factory=lambda *_: StubApp()
    )
    monkeypatch.setattr(session, "_try_azure_cli_token", lambda: None)
    monkeypatch.setattr(session, "_try_wam_token", lambda: None)

    with pytest.raises(
        RuntimeError, match="Unable to acquire Microsoft Graph access token"
    ):
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


def test_account_hint_never_uses_other_cached_account():
    class OtherAccountApp(StubApp):
        def get_accounts(self):
            return [{"username": "other@example.com"}]

        def acquire_token_silent_with_error(self, scopes, account, force_refresh=False):
            raise AssertionError("nonmatching cached account was used")

    app = OtherAccountApp()
    session = GraphAuthSession(
        build_config(mode=AuthMode.WAM, account_hint="user@example.com"),
        app_factory=lambda *_: app,
    )
    assert session.acquire_token() == "interactive-token"
    assert app.calls == ["interactive"]
    assert app.interactive_kwargs["login_hint"] == "user@example.com"


def test_azure_cli_requests_configured_tenant_and_scopes(monkeypatch):
    from mtg_microsoft_auth import session as session_module

    token = synthetic_token()
    commands = []
    monkeypatch.setattr(session_module.shutil, "which", lambda name: "/synthetic/az")

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=token)

    monkeypatch.setattr(session_module.subprocess, "run", fake_run)
    auth = GraphAuthSession(
        build_config(mode=AuthMode.AZURE_CLI, account_hint="user@example.com"),
        app_factory=lambda *_: StubApp(),
    )
    assert auth.acquire_token() == token
    assert commands[0][3:6] == [
        "--scope",
        "https://graph.microsoft.com/Tasks.Read",
        "https://graph.microsoft.com/Tasks.ReadWrite",
    ]
    assert ["--tenant", auth.config.tenant_id] == commands[0][6:8]


@pytest.mark.parametrize(
    "requested_tenant,token_tenant,expected",
    [
        ("consumers", "9188040d-6c67-4c5b-b112-36a304b66dad", True),
        ("consumers", "22222222-2222-2222-2222-222222222222", False),
        ("organizations", "9188040d-6c67-4c5b-b112-36a304b66dad", False),
        ("organizations", "22222222-2222-2222-2222-222222222222", True),
    ],
)
def test_azure_cli_tenant_aliases(requested_tenant, token_tenant, expected):
    auth = GraphAuthSession(
        build_config(mode=AuthMode.AZURE_CLI, tenant_id=requested_tenant),
        app_factory=lambda *_: StubApp(),
    )
    assert (
        auth._azure_cli_token_matches_config(synthetic_token(tid=token_tenant))
        is expected
    )


def test_azure_cli_timeout_returns_no_token(monkeypatch):
    from mtg_microsoft_auth import session as session_module

    monkeypatch.setattr(session_module.shutil, "which", lambda name: "/synthetic/az")

    def timeout_run(command, **kwargs):
        assert kwargs["timeout"] == 60
        raise session_module.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(session_module.subprocess, "run", timeout_run)
    auth = GraphAuthSession(
        build_config(mode=AuthMode.AZURE_CLI), app_factory=lambda *_: StubApp()
    )
    with pytest.raises(
        RuntimeError, match="Unable to acquire Microsoft Graph access token"
    ):
        auth.acquire_token()


@pytest.mark.parametrize(
    "claim,value",
    [
        ("aud", "https://management.azure.com"),
        ("azp", "33333333-3333-3333-3333-333333333333"),
        ("tid", "44444444-4444-4444-4444-444444444444"),
        ("scp", "Tasks.Read"),
        ("scp", "Tasks.Read Tasks.ReadWrite Mail.Read"),
        ("preferred_username", "other@example.com"),
    ],
)
def test_azure_cli_rejects_mismatched_identity_or_grants(monkeypatch, claim, value):
    from mtg_microsoft_auth import session as session_module

    token = synthetic_token(**{claim: value})
    monkeypatch.setattr(session_module.shutil, "which", lambda name: "/synthetic/az")
    monkeypatch.setattr(
        session_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=token),
    )
    auth = GraphAuthSession(
        build_config(mode=AuthMode.AZURE_CLI, account_hint="user@example.com"),
        app_factory=lambda *_: StubApp(),
    )
    with pytest.raises(
        RuntimeError, match="does not match configured Graph identity or scopes"
    ):
        auth.acquire_token()


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
