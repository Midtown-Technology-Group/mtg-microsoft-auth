from pathlib import Path

import pytest

from mtg_microsoft_auth.models import AuthConfig, AuthMode
from mtg_microsoft_auth.session import GraphAuthSession


class StubApp:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_accounts(self):
        return [{"username": "user@example.com"}]

    def acquire_token_silent_with_error(self, scopes, account, force_refresh=False):
        self.calls.append("wam")
        return None

    def acquire_token_interactive(self, scopes, **kwargs):
        self.calls.append("interactive")
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
